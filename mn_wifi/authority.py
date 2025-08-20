"""WiFi Authority Node implementation for FastPay simulation."""

from __future__ import annotations

import logging
import threading
import time
from queue import Queue
from typing import Any, Dict, List, Optional, Set, Protocol
from uuid import UUID, uuid4
from datetime import datetime

from mn_wifi.node import Station
from mn_wifi.link import IntfWireless
from mn_wifi.services.core.config import SUPPORTED_TOKENS

from mn_wifi.baseTypes import (
    AccountOffchainState,
    Address,
    AuthorityState,
    ConfirmationOrder,
    SignedTransferOrder,
    NetworkMetrics,
    NodeType,
    TransactionStatus,
    TransferOrder,
)
from mn_wifi.messages import (
    ConfirmationRequestMessage,
    Message,
    MessageType,
    SyncRequestMessage,
    TransferRequestMessage,
    TransferResponseMessage,
)
from mn_wifi.client import TransportKind  # Enum shared across modules

# Dedicated transport implementations
from mn_wifi.transport import NetworkTransport, TransportKind
from mn_wifi.tcp import TCPTransport
from mn_wifi.udp import UDPTransport
from mn_wifi.wifiDirect import WiFiDirectTransport

from mn_wifi.metrics import MetricsCollector
from mn_wifi.authorityLogger import AuthorityLogger
from mn_wifi.services.blockchain_client import BlockchainClient, TokenBalance
from mn_wifi.services.core.config import settings
from decimal import Decimal

DEFAULT_BALANCES = {
    "0x0000000000000000000000000000000000000000": TokenBalance(
        token_address="0x0000000000000000000000000000000000000000",
        token_symbol="XTZ",
        meshpay_balance=0.0,
        wallet_balance=0.0,
        total_balance=0.0,
        decimals=18
    ),
    settings.wtz_contract_address: TokenBalance(
        token_address=settings.wtz_contract_address,
        token_symbol="WTZ",
        meshpay_balance=0.0,
        wallet_balance=0.0,
        total_balance=0.0,
        decimals=18
    ),
    settings.usdt_contract_address: TokenBalance(
        token_address=settings.usdt_contract_address,
        token_symbol="USDT",
        meshpay_balance=0.0,
        wallet_balance=0.0,
        total_balance=0.0,
        decimals=6
    ),
    settings.usdc_contract_address: TokenBalance(
        token_address=settings.usdc_contract_address,
        token_symbol="USDC",
        meshpay_balance=0.0,
        wallet_balance=0.0,
        total_balance=0.0,
        decimals=6
    ),
}
class WiFiAuthority(Station):
    """Authority node that runs on mininet-wifi host, inheriting from Station."""
    
    def __init__(
        self,
        name: str,
        committee_members: Set[str],
        shard_assignments: Optional[Set[str]] = None,
        ip: str = '10.0.0.1/8',
        port: int = 8080,
        position: Optional[List[float]] = None,
        **params
    ) -> None:
        """Initialize WiFi Authority node.
        
        Args:
            name: Authority name
            committee_members: Set of committee member names
            shard_assignments: Optional set of shard assignments
            ip: IP address for the node
            position: Position of the node [x, y, z]
            **params: Additional parameters for Station
        """
        # Extract transport configuration parameters **before** updating default_params so that
        # we don't forward them to Station.__init__, which would not recognise them.

        transport_kind = params.pop("transport_kind", TransportKind.TCP)
        transport: Optional[NetworkTransport] = params.pop("transport", None)

        default_params = {
            'ip': ip,
            'position': position or [0, 0, 0],
            'range': 100,  # WiFi range in meters
            'txpower': 20,  # Transmission power
            'antennaGain': 5,  # Antenna gain
        }
        default_params.update(params)
        
        # Initialize the Station base class
        super().__init__(name, **default_params)

        # Configure logging
        self.logger = AuthorityLogger(name)

        # Use the global blockchain client instance
        self.blockchain_client = BlockchainClient(self.logger)

        # Create address from mininet-wifi node information
        self.address = Address(
            node_id=name,
            ip_address=ip.split('/')[0],
            port=port,  
            node_type=NodeType.AUTHORITY
        )

        # FastPay specific attributes
        self.state = AuthorityState(
            name=name,
            address=self.address,
            shard_assignments=shard_assignments or set(),
            accounts={},
            committee_members=committee_members,
            last_sync_time=time.time(),
            authority_signature=f"signed_by_authority_{name}",
            stake=0
        )
        
        self.p2p_connections: Dict[str, Address] = {}
        self.message_queue: Queue[Message] = Queue()
        self.performance_metrics = MetricsCollector()
        
        self._running = False
        self._message_handler_thread: Optional[threading.Thread] = None
        self._blockchain_sync_thread: Optional[threading.Thread] = None
        
        # ------------------------------------------------------------------
        # Transport selection (default = TCP for backward-compatibility)
        # ------------------------------------------------------------------

        if transport is not None:
            self.transport: NetworkTransport = transport
        else:
            if transport_kind == TransportKind.TCP:
                self.transport = TCPTransport(self, self.address)
            elif transport_kind == TransportKind.UDP:
                self.transport = UDPTransport(self, self.address)
            elif transport_kind == TransportKind.WIFI_DIRECT:
                self.transport = WiFiDirectTransport(self, self.address)
            else:
                raise ValueError(f"Unsupported transport kind: {transport_kind}")

    def start_fastpay_services(self) -> bool:
        """Boot-strap background processing threads and ready the chosen transport.

        The method preserves the previous external behaviour: it must be called explicitly after
        the authority instance is added to Mininet-WiFi so that the node's namespace exists.
        """

        # Connect transport (if the implementation supports/needs it)
        if hasattr(self.transport, "connect"):
            try:
                if not self.transport.connect():  # type: ignore[attr-defined]
                    self.logger.error("Failed to connect transport")
                    return False
            except Exception as exc:  # pragma: no cover
                self.logger.error(f"Transport connect error: {exc}")
                return False

        self._running = True

        # Spawn background threads -----------------------------------------------------------
        self._message_handler_thread = threading.Thread(
            target=self._message_handler_loop,
            daemon=True,
        )
        self._message_handler_thread.start()

        # Start blockchain sync thread
        self._blockchain_sync_thread = threading.Thread(
            target=self._blockchain_sync_loop,
            daemon=True,
        )
        self._blockchain_sync_thread.start()

        self.logger.info(f"Authority {self.name} started successfully")
        return True
    
    def stop_fastpay_services(self) -> None:
        """Stop the FastPay authority services."""
        self._running = False
        if hasattr(self.transport, "disconnect"):
            try:
                self.transport.disconnect()  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover
                pass
        
        if self._message_handler_thread:
            self._message_handler_thread.join(timeout=5.0)
        if self._blockchain_sync_thread:
            self._blockchain_sync_thread.join(timeout=5.0)
        self.logger.info(f"Authority {self.name} stopped")
    
    async def update_account_balance(self) -> None:
        """Update account balance.
        
        Args:
            account_address: Address of the account

        """
        try:
            for account in self.state.accounts.keys():
                confirmed_transfers = self.state.accounts[account].confirmed_transfers.values()
                for transfer in confirmed_transfers:
                    # Convert ISO 8601 timestamp string → UNIX timestamp
                    iso_timestamp = transfer.transfer_order.timestamp  # e.g., '2025-08-03T00:36:41.565Z'
                    dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
                    unix_timestamp = int(dt.timestamp())

                    # Parse the amount with decimals
                    for token_symbol, token_config in SUPPORTED_TOKENS.items():
                        if token_config['address'] == transfer.transfer_order.token_address:
                            parsed_amount = int(transfer.transfer_order.amount * (10 ** token_config['decimals']))
                            break

                    # Create the transferOrder tuple
                    transfer_order = (
                        str(transfer.transfer_order.order_id),              # string
                        str(transfer.transfer_order.sender),                # address
                        str(transfer.transfer_order.recipient),             # address
                        parsed_amount,                # uint256
                        str(transfer.transfer_order.token_address),         # address
                        int(transfer.transfer_order.sequence_number),       # uint256
                        unix_timestamp,                                     # uint256
                        str(transfer.transfer_order.signature or "0x"),     # string, default to "0x"
                    )

                    # Make sure authority signatures are strings (not bytes or None)
                    authority_signatures = [str(sig or "0x") for sig in transfer.authority_signatures]

                    # Final structure to match: ((...), [...])
                    confirmation_order = (transfer_order, authority_signatures)

                    # Submit to blockchain
                    await self.blockchain_client.update_account_balance(confirmation_order)

        except Exception as e:
            self.logger.error(f"Error updating account balance: {e}")

    async def sync_account_from_blockchain(self) -> None:
        """Sync all registered accounts from blockchain using blockchain client."""
        try:
            # Use blockchain client to sync all accounts
            all_accounts_data = await self.blockchain_client.sync_all_accounts()

            # Update local state with blockchain data
            for account_address, balances in all_accounts_data.items():
                await self._update_local_account_state(account_address, balances)
                
        except Exception as e:
            self.logger.error(f"Error syncing accounts from blockchain: {e}")
    
    async def _update_local_account_state(self, account_address: str, balances: Dict[str, TokenBalance]) -> None:
        """Update local account state with blockchain data.
        
        Args:
            account_address: The account address
            balances: Dictionary mapping token addresses to balances
        """
        try:
            # Get account info from blockchain
            account_info = await self.blockchain_client.get_account_info(account_address)

            if not account_info or not account_info.is_registered:
                self.logger.warning(f"Account {account_address} not registered on blockchain")
                return

            # Update or create account state
            if account_address not in self.state.accounts:
                self.state.accounts[account_address] = AccountOffchainState(
                    address=account_address,
                    balances=balances,
                    last_update=time.time(),
                    pending_confirmation=None,
                    confirmed_transfers={},
                    sequence_number=0,
                )
                self.logger.info(f"Created new account state for {account_address}")
            else:
                account = self.state.accounts[account_address]
                account.balances = balances
                account.last_update = time.time()
                self.logger.debug(f"Updated account state for {account_address}")

        except Exception as e:
            self.logger.error(f"Error updating local account state for {account_address}: {e}")

    def handle_transfer_order(self, transfer_order: TransferOrder) -> TransferResponseMessage:
        """Handle transfer order from client.
        
        Args:
            transfer_order: Transfer order to process
            
        Returns:
            Transfer response message
        """
        try:
            # Validate transfer order
            if not self._validate_transfer_order(transfer_order):
                return TransferResponseMessage(
                    transfer_order=transfer_order,
                    success=False,
                    error_message="Invalid transfer order",
                    authority_signature=self.state.authority_signature
                )
            
            # Add to pending transfers
            self.state.accounts[transfer_order.sender].pending_confirmation = SignedTransferOrder(
                order_id=transfer_order.order_id,
                transfer_order=transfer_order,
                authority_signature=self.state.authority_signature,
                timestamp=time.time()
            )
            
            # Create recipient account if it doesn't exist
            if transfer_order.recipient not in self.state.accounts:
                self.state.accounts[transfer_order.recipient] = AccountOffchainState(
                    address=transfer_order.recipient,
                    balances=DEFAULT_BALANCES,
                    sequence_number=0,
                    last_update=time.time(),
                    pending_confirmation={},
                    confirmed_transfers={},
                )
            
            self.performance_metrics.record_transaction()

            return TransferResponseMessage(
                transfer_order=transfer_order,
                success=True,
                authority_signature=self.state.authority_signature,
                error_message=None
            )
            
        except Exception as e:
            self.logger.error(f"Error handling transfer order: {e}")
            self.performance_metrics.record_error()
            return TransferResponseMessage(
                transfer_order=transfer_order,
                success=False,
                error_message=f"Internal error: {str(e)}"
            )
    
    def handle_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Handle confirmation order from committee.
        
        Args:
            confirmation_order: Confirmation order to process
            
        Returns:
            True if handled successfully, False otherwise
        """
        try:
            # Check if the confirmation order is valid
            if not self._validate_confirmation_order(confirmation_order):
                return False
            
            # Store confirmation order
            account = self.state.accounts[confirmation_order.transfer_order.sender]

            account.confirmed_transfers[str(confirmation_order.order_id)] = confirmation_order

            # Remove from pending
            account.pending_confirmation = None
            
            # Update confirmation status
            confirmation_order.status = TransactionStatus.CONFIRMED

            # ------------------------------------------------------------------
            # Apply final balance changes based on the confirmed transfer
            # ------------------------------------------------------------------
            # Update recipient balance
            transfer = confirmation_order.transfer_order

            sender = self.state.accounts.setdefault(
                transfer.sender,
                AccountOffchainState(
                    address=transfer.sender,
                    balances=DEFAULT_BALANCES,
                    sequence_number=0,
                    last_update=time.time(),
                    pending_confirmation=None,
                    confirmed_transfers={},
                ),
            )
            recipient = self.state.accounts.setdefault(
                transfer.recipient,
                AccountOffchainState(
                    address=transfer.recipient,
                    balances=DEFAULT_BALANCES,
                    sequence_number=0,
                    last_update=time.time(),
                    pending_confirmation=None,
                    confirmed_transfers={},
                ),
            )

            # Deduct / credit
            sender.balances[transfer.token_address].meshpay_balance -= transfer.amount
            sender.sequence_number += 1
            sender.last_update = time.time()

            recipient.balances[transfer.token_address].meshpay_balance += transfer.amount
            recipient.last_update = time.time()

            # ------------------------------------------------------------------

            self.logger.info(f"Confirmation order {confirmation_order.order_id} processed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error handling confirmation order: {e}")
            self.performance_metrics.record_error()
            return False
    
    def get_account_balance(self, account_address: str) -> Optional[int]:
        """Get account balance.
        
        Args:
            account_address: Address of the account
            
        Returns:
            Account balance or None if account not found
        """
        account = self.state.accounts.get(account_address)
        return account.balances if account else None
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics.
        
        Returns:
            Dictionary containing performance stats
        """
        return self.performance_metrics.get_stats()
    
    def trigger_blockchain_sync(self) -> None:
        """Manually trigger blockchain sync for all registered accounts.
        
        This method can be called externally to force a blockchain sync
        without waiting for the next scheduled interval.
        """
        if not self._running:
            self.logger.warning("Authority not running, cannot trigger blockchain sync")
            return
        
        self.logger.info("Manually triggering blockchain sync")
        
        try:
            import asyncio
            asyncio.run(self.sync_account_from_blockchain())
        except Exception as e:
            self.logger.error(f"Error during manual blockchain sync: {e}")
        
        self.logger.info(f"Manual blockchain sync completed for {len(self.state.accounts)} accounts")
    
    def _validate_transfer_order(self, transfer_order: TransferOrder) -> bool:
        """Validate a transfer order.
        
        Args:
            transfer_order: Transfer order to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Basic validation checks
        if transfer_order.amount <= 0:
            return False
        
        if transfer_order.sender == transfer_order.recipient:
            return False
        
        if not transfer_order.sender or not transfer_order.recipient:
            return False
        
        # Check sequence number
        sender_account = self.state.accounts.get(transfer_order.sender)
        if sender_account and int(transfer_order.sequence_number) < int(sender_account.sequence_number):
            return False
        
        token_balance = sender_account.balances.get(transfer_order.token_address)   
        meshpay_balance = int(token_balance.meshpay_balance)
        
        if meshpay_balance < transfer_order.amount:
            return False
        
        return True
    
    def _validate_confirmation_order(self, confirmation_order: ConfirmationOrder) -> bool:
        """Validate a confirmation order.
        
        Args:
            confirmation_order: Confirmation order to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check if the confirmation order is valid
        if not self._validate_transfer_order(confirmation_order.transfer_order):
            return False        
        
        account = self.state.accounts.get(confirmation_order.transfer_order.sender)

        # Check if already confirmed
        if (
            account
            and account.confirmed_transfers
            and confirmation_order.order_id in account.confirmed_transfers
        ):
            return False

        if account.pending_confirmation and str(account.pending_confirmation.order_id) != str(confirmation_order.transfer_order.order_id):
            return False

        #TODO: Check the signature of the confirmation order
        # if not confirmation_order.authority_signatures:
        #     return False

        return True
    
    def _message_handler_loop(self) -> None:
        """Main message handling loop."""
        while self._running:
            try:
                message = self.transport.receive_message(timeout=1.0)
                if message:
                    self._process_message(message)
            except Exception as e:
                self.logger.error(f"Error in message handler loop: {e}")
                time.sleep(0.1)
    
    def _process_message(self, message: Message) -> None:
        """Process incoming message.
        
        Args:
            message: Message to process
        """
        try:
            if message.message_type == MessageType.TRANSFER_REQUEST:
                request = TransferRequestMessage.from_payload(message.payload)
                response = self.handle_transfer_order(request.transfer_order)
                
                # Send response back
                response_message = Message(
                    message_id=uuid4(),
                    message_type=MessageType.TRANSFER_RESPONSE,
                    sender=self.address,
                    recipient=message.sender,
                    timestamp=time.time(),
                    payload=response.to_payload()
                )
                self.transport.send_message(response_message, message.sender)
                
            elif message.message_type == MessageType.CONFIRMATION_REQUEST:
                request = ConfirmationRequestMessage.from_payload(message.payload)
                self.handle_confirmation_order(request.confirmation_order)
                
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    def _blockchain_sync_loop(self) -> None:
        """Periodic blockchain synchronization loop."""
        first_run = True
        while self._running:
            try:
                # Wait for the sync interval (skip on first run)
                if not first_run:
                    time.sleep(settings.blockchain_sync_interval)
                
                if not self._running:
                    break
                
                # Sync all registered accounts from blockchain
                try:
                    # Use asyncio.run to call the async method from sync context
                    import asyncio
                    asyncio.run(self.sync_account_from_blockchain())
                except Exception as e:
                    self.logger.error(f"Error in blockchain sync cycle: {e}")
                
                # Mark that we've completed the first run
                first_run = False
                
            except Exception as e:
                self.logger.error(f"Error in blockchain sync loop: {e}")
                # Wait a bit before retrying
                time.sleep(10) 