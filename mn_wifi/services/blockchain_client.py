"""
Blockchain client for interacting with FastPay smart contracts on Etherlink.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from dataclasses import dataclass

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from mn_wifi.services.abis import MeshPayABI, ERC20ABI
from mn_wifi.services.core.config import settings, SUPPORTED_TOKENS
from mn_wifi.authorityLogger import AuthorityLogger

@dataclass
class AccountInfo:
    """Account information from smart contract."""
    address: str
    is_registered: bool
    registration_time: int
    last_redeemed_sequence: int

@dataclass
class TokenBalance:
    """Token balance information."""
    token_symbol: str
    token_address: str
    wallet_balance: int
    meshpay_balance: int
    total_balance: int
    decimals: int

@dataclass
class ContractStats:
    """Overall contract statistics."""
    total_accounts: int
    total_native_balance: int
    total_token_balances: Dict[str, int]

class BlockchainClient:
    """Client for interacting with Etherlink blockchain and FastPay contracts."""
    
    def __init__(self, logger: AuthorityLogger):
        """Initialize blockchain client with Web3 connection."""
        self.w3: Optional[Web3] = None
        self.meshpay_contract = None
        self.account = None
        self.logger = logger
        self._initialize_connection()
    
    def _initialize_connection(self) -> None:
        """Initialize Web3 connection to Etherlink."""
        try:
            # Connect to Etherlink RPC
            self.w3 = Web3(Web3.HTTPProvider(settings.rpc_url))
            
            # Add PoA middleware for Etherlink
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            
            # Verify connection
            if not self.w3.is_connected():
                raise ConnectionError(f"Failed to connect to {settings.rpc_url}")
            
            self.logger.info(f"Connected to blockchain: {settings.chain_name} (Chain ID: {settings.chain_id})")

            # Initialize FastPay contract if address is configured
            if settings.meshpay_contract_address:
                self.meshpay_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(settings.meshpay_contract_address),
                    abi=MeshPayABI
                )
                self.logger.info(f"FastPay contract initialized at {settings.meshpay_contract_address}")
            else:
                self.logger.warning("MESHPAY_CONTRACT_ADDRESS not configured. FastPay contract will not be available.")
                self.logger.info("To enable FastPay functionality, set MESHPAY_CONTRACT_ADDRESS environment variable")
            
            # Initialize backend account if private key is provided
            if settings.backend_private_key:
                self.account = Account.from_key(settings.backend_private_key)
                self.logger.info(f"Backend account initialized: {self.account.address}")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize blockchain connection: {e}")
            self.w3 = None
    
    async def get_account_info(self, address: str) -> Optional[AccountInfo]:
        """Get account information from FastPay contract."""
        if not self.meshpay_contract:
            self.logger.error("FastPay contract not initialized")
            return None
        
        try:
            address = Web3.to_checksum_address(address)
            
            # Get account info from contract
            account_data = self.meshpay_contract.functions.getAccountInfo(address).call()
            
            return AccountInfo(
                address=address,
                is_registered=account_data[0],
                registration_time=account_data[1],
                last_redeemed_sequence=account_data[2]
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get account info for {address}: {e}")
            return None
    
    async def get_account_balances(self, address: str) -> List[TokenBalance]:
        """Get all token balances for an account."""
        if not self.w3:
            self.logger.error("Web3 not initialized")
            return {}
        
        balances = {}
        address = Web3.to_checksum_address(address)
        
        for token_symbol, token_config in SUPPORTED_TOKENS.items():
            try:
                token_address = token_config['address']
                decimals = token_config['decimals']
                
                # Initialize balances
                wallet_balance = 0
                meshpay_balance = 0
                
                # Get wallet balance
                if token_config['is_native']:
                    # Native XTZ balance - this should always work
                    try:
                        checksum_address = Web3.to_checksum_address(address)
                        wallet_balance_wei = self.w3.eth.get_balance(checksum_address)
                        wallet_balance = self._wei_to_human(wallet_balance_wei, decimals)
                    except Exception as e:
                        self.logger.error(f"Failed to get {token_symbol} wallet balance for {address}: {e}")
                        wallet_balance = 0
                        
                else:
                    # ERC20 token balance - check if token is actually deployed
                    try:
                        if token_address:
                            token_address_checksum = Web3.to_checksum_address(token_address)
                            
                            # Check if contract exists
                            code = self.w3.eth.get_code(token_address_checksum)
                            if code and code != b'':
                                # Contract exists, try to get balance
                                token_contract = self.w3.eth.contract(
                                    address=token_address_checksum,
                                    abi=ERC20ABI
                                )
                                wallet_balance_wei = token_contract.functions.balanceOf(address).call()
                                wallet_balance = self._wei_to_human(wallet_balance_wei, decimals)
                            else:
                                self.logger.warning(f"{token_symbol} contract not deployed at {token_address}")
                                wallet_balance = 0
                        else:
                            self.logger.warning(f"{token_symbol} contract address not configured")
                            wallet_balance = 0
                            
                    except Exception as e:
                        self.logger.error(f"Failed to get {token_symbol} wallet balance for {address}: {e}")
                        wallet_balance = 0
                
                # Get MeshPay balance (only if MeshPay contract is available)
                if self.meshpay_contract:
                    try:
                        meshpay_balance_wei = self.meshpay_contract.functions.getAccountBalance(
                            address, token_address
                        ).call()
                        meshpay_balance = self._wei_to_human(meshpay_balance_wei, decimals)
                        
                    except Exception as e:
                        self.logger.error(f"Failed to get {token_symbol} MeshPay balance for {address}: {e}")
                        meshpay_balance = 0
                else:
                    self.logger.warning("MeshPay contract not available, using 0 for MeshPay balances")
                    meshpay_balance = 0
                
                # Calculate total
                total_balance = str(Decimal(wallet_balance) + Decimal(meshpay_balance))
                
                balances[token_address] = TokenBalance(
                    token_symbol=token_symbol,
                    token_address=token_address,
                    wallet_balance=wallet_balance,
                    meshpay_balance=meshpay_balance,
                    total_balance=total_balance,
                    decimals=decimals
                )
                
            except Exception as e:
                self.logger.error(f"Failed to process {token_symbol} balance for {address}: {e}")
                # Add zero balance as fallback
                balances[token_address] = TokenBalance(
                    token_symbol=token_symbol,
                    token_address=token_config['address'],
                    wallet_balance=0,
                    meshpay_balance=0,
                    total_balance=0,
                    decimals=token_config['decimals']
                )
        
        return balances
    
    async def get_contract_stats(self) -> Optional[ContractStats]:
        """Get overall contract statistics."""
        if not self.meshpay_contract:
            self.logger.error("FastPay contract not initialized")
            return None
        
        try:
            # Get total accounts
            total_accounts = self.meshpay_contract.functions.getRegisteredAccounts().call()
            
            # Get total balances for each token
            total_token_balances = {}
            total_native_balance = 0
            
            for token_symbol, token_config in SUPPORTED_TOKENS.items():
                token_address = Web3.to_checksum_address(token_config['address'])
                # Note: totalBalance function was removed, so we'll calculate from individual accounts
                total_balance = 0
                
                if token_config['is_native']:
                    total_native_balance = total_balance
                else:
                    total_token_balances[token_symbol] = total_balance
            
            return ContractStats(
                total_accounts=len(total_accounts),
                total_native_balance=total_native_balance,
                total_token_balances=total_token_balances
            )
            
        except Exception as e:
            self.logger.error(f"Failed to get contract stats: {e}")
            return None
    
    async def get_registered_accounts(self) -> List[str]:
        """Get all registered account addresses from the blockchain."""
        if not self.meshpay_contract:
            self.logger.error("FastPay contract not initialized")
            return []
        
        try:
            accounts = self.meshpay_contract.functions.getRegisteredAccounts().call()
            return [Web3.to_checksum_address(account) for account in accounts]
        except Exception as e:
            self.logger.error(f"Failed to get registered accounts: {e}")
            return []
    
    async def get_meshpay_balance(self, account_address: str, token_address: str) -> int:
        """Get account balance for a specific token.
        
        Args:
            account_address: The account address
            token_address: The token address (use NATIVE_TOKEN for XTZ)
            
        Returns:
            Balance in wei
        """
        if not self.meshpay_contract:
            self.logger.error("FastPay contract not initialized")
            return 0
        
        try:
            account_address = Web3.to_checksum_address(account_address)
            token_address = Web3.to_checksum_address(token_address)
            
            balance = self.meshpay_contract.functions.getAccountBalance(
                account_address, token_address
            ).call()
            
            return balance
        except Exception as e:
            self.logger.error(f"Failed to get balance for {account_address} token {token_address}: {e}")
            return 0
    
    async def sync_all_accounts(self) -> Dict[str, Dict[str, int]]:
        """Sync all registered accounts with their balances for all supported tokens.
        
        Returns:
            Dictionary mapping account addresses to their token balances
        """
        if not self.meshpay_contract:
            self.logger.error("FastPay contract not initialized")
            return {}
        
        try:
            # Get all registered accounts
            registered_accounts = await self.get_registered_accounts()
            self.logger.info(f"Found {len(registered_accounts)} registered accounts on blockchain")
            
            # Sync each account
            all_accounts_data = {}
            for account_address in registered_accounts:
                account_data = await self._sync_single_account(account_address)
                if account_data:
                    all_accounts_data[account_address] = account_data
            
            self.logger.info(f"Successfully synced {len(all_accounts_data)} accounts")
            return all_accounts_data
            
        except Exception as e:
            self.logger.error(f"Error syncing all accounts from blockchain: {e}")
            return {}
    
    async def _sync_single_account(self, account_address: str) -> Optional[Dict[str, int]]:
        """Sync a single account's state from blockchain.
        
        Args:
            account_address: The account address to sync
            
        Returns:
            Dictionary mapping token addresses to balances, or None if failed
        """
        try:
            # Get account info from blockchain
            account_info = await self.get_account_info(account_address)
            
            if not account_info or not account_info.is_registered:
                self.logger.warning(f"Account {account_address} not registered on blockchain")
                return None

            # Get balances for all supported tokens
            balances = await self.get_account_balances(account_address)
            self.logger.debug(f"Synced account {account_address} with {len(balances)} token balances")
            return balances

        except Exception as e:
            self.logger.error(f"Error syncing account {account_address}: {e}")
            return None
    
    async def get_recent_events(self, event_name: str, from_block: int = None, limit: int = 100) -> List[Dict]:
        """Get recent contract events."""
        if not self.meshpay_contract:
            return []
        
        try:
            if from_block is None:
                # Get events from last 1000 blocks
                latest_block = self.w3.eth.block_number
                from_block = max(0, latest_block - 1000)
            
            event_filter = getattr(self.meshpay_contract.events, event_name).create_filter(
                fromBlock=from_block,
                toBlock='latest'
            )
            
            events = event_filter.get_all_entries()
            
            # Convert events to dict format
            event_list = []
            for event in events[-limit:]:  # Get latest events up to limit
                event_data = {
                    'event': event.event,
                    'block_number': event.blockNumber,
                    'transaction_hash': event.transactionHash.hex(),
                    'args': dict(event.args)
                }
                event_list.append(event_data)
            
            return event_list
            
        except Exception as e:
            self.logger.error(f"Failed to get {event_name} events: {e}")
            return []
    
    def _wei_to_human(self, wei_amount: int, decimals: int) -> int:
        """Convert wei amount to human-readable format."""
        return int(Decimal(wei_amount) / Decimal(10 ** decimals))
    
    def _human_to_wei(self, human_amount: Union[str, Decimal], decimals: int) -> int:
        """Convert human-readable amount to wei."""
        return int(Decimal(human_amount) * Decimal(10 ** decimals))
    
    async def health_check(self) -> Dict[str, Any]:
        """Check blockchain connection health."""
        health_status = {
            'connected': False,
            'chain_id': None,
            'latest_block': None,
            'meshpay_contract': False,
            'error': None
        }
        
        try:
            if self.w3 and self.w3.is_connected():
                health_status['connected'] = True
                health_status['chain_id'] = self.w3.eth.chain_id
                health_status['latest_block'] = self.w3.eth.block_number
                
                if self.meshpay_contract:
                    # Test contract call
                    registered_accounts = self.meshpay_contract.functions.getRegisteredAccounts().call()
                    health_status['meshpay_contract'] = True
                    health_status['total_accounts'] = len(registered_accounts)
                    
        except Exception as e:
            health_status['error'] = str(e)
            self.logger.error(f"Blockchain health check failed: {e}")
        
        return health_status
