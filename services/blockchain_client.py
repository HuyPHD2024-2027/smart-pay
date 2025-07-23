"""
Blockchain client for interacting with FastPay smart contracts on Etherlink.
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from decimal import Decimal
from dataclasses import dataclass

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

_ABI_DIR: Path = Path(__file__).resolve().parent.parent / "abis"

def _load_abi(filename: str) -> List[Dict[str, Any]]:
    """Return ABI list from the given JSON file.

    The JSON may either be a raw list (standard Hardhat export) or an object
    with an ``abi`` field (solidity-coverage & Foundry style). The helper
    normalises both cases and always returns the ABI array.
    """

    with open(_ABI_DIR / filename, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    if isinstance(data, list):  # Hardhat style export
        return data

    # Object export: { "abi": [...] }
    if "abi" in data and isinstance(data["abi"], list):
        return data["abi"]

    raise ValueError(f"Unsupported ABI format in {_ABI_DIR / filename}")


# Expose ABIs as module-level constants (preserves previous variable names)
MeshPayABI: List[Dict[str, Any]] = _load_abi("MeshPayMVP.json")
MeshPayAuthoritiesABI: List[Dict[str, Any]] = _load_abi("MeshPayAuthorities.json")
ERC20ABI: List[Dict[str, Any]] = _load_abi("ERC20.json")

# ---------------------------------------------------------------------------

from ..core.config import settings, SUPPORTED_TOKENS

logger = logging.getLogger(__name__)

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
    wallet_balance: str  # In human-readable format
    meshpay_balance: str  # In human-readable format
    total_balance: str
    decimals: int

@dataclass
class ContractStats:
    """Overall contract statistics."""
    total_accounts: int
    total_native_balance: str
    total_token_balances: Dict[str, str]

class BlockchainClient:
    """Client for interacting with Etherlink blockchain and FastPay contracts."""
    
    def __init__(self):
        """Initialize blockchain client with Web3 connection."""
        self.w3: Optional[Web3] = None
        self.meshpay_contract = None
        self.account = None
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
            
            logger.info(f"Connected to blockchain: {settings.chain_name} (Chain ID: {settings.chain_id})")
            
            # Initialize FastPay contract if address is configured
            if settings.meshpay_contract_address:
                self.meshpay_contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(settings.meshpay_contract_address),
                    abi=MeshPayABI
                )
                logger.info(f"FastPay contract initialized at {settings.meshpay_contract_address}")
            
            # Initialize backend account if private key is provided
            if settings.backend_private_key:
                self.account = Account.from_key(settings.backend_private_key)
                logger.info(f"Backend account initialized: {self.account.address}")
                
        except Exception as e:
            logger.error(f"Failed to initialize blockchain connection: {e}")
            self.w3 = None
    
    async def get_account_info(self, address: str) -> Optional[AccountInfo]:
        """Get account information from FastPay contract."""
        if not self.meshpay_contract:
            logger.error("FastPay contract not initialized")
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
            logger.error(f"Failed to get account info for {address}: {e}")
            return None
    
    async def get_account_balances(self, address: str) -> List[TokenBalance]:
        """Get all token balances for an account."""
        if not self.w3:
            logger.error("Web3 not initialized")
            return []
        
        balances = []
        address = Web3.to_checksum_address(address)
        
        for token_symbol, token_config in SUPPORTED_TOKENS.items():
            try:
                token_address = token_config['address']
                decimals = token_config['decimals'] if token_config['is_native'] else 0
                
                # Initialize balances
                wallet_balance = "0"
                meshpay_balance = "0"
                
                # Get wallet balance
                if token_config['is_native']:
                    # Native XTZ balance - this should always work
                    try:
                        checksum_address = Web3.to_checksum_address(address)
                        wallet_balance_wei = self.w3.eth.get_balance(checksum_address)
                        wallet_balance = self._wei_to_human(wallet_balance_wei, decimals)
                        logger.info(f"Successfully got {token_symbol} wallet balance: {wallet_balance}")
                    except Exception as e:
                        logger.error(f"Failed to get {token_symbol} wallet balance for {address}: {e}")
                        wallet_balance = "0"
                        
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
                                wallet_balance = self._wei_to_human(wallet_balance_wei, 0)
                                logger.info(f"Successfully got {token_symbol} wallet balance: {wallet_balance}")
                            else:
                                logger.warning(f"{token_symbol} contract not deployed at {token_address}")
                                wallet_balance = "0"
                        else:
                            logger.warning(f"{token_symbol} contract address not configured")
                            wallet_balance = "0"
                            
                    except Exception as e:
                        logger.error(f"Failed to get {token_symbol} wallet balance for {address}: {e}")
                        wallet_balance = "0"
                
                # Get MeshPay balance (only if MeshPay contract is available)
                if self.meshpay_contract:
                    try:
                        # Use the correct token address for MeshPay contract
                        if token_config['is_native']:
                            # Use NATIVE_TOKEN address (0x0000000000000000000000000000000000000000) for XTZ
                            meshpay_token_address = '0x0000000000000000000000000000000000000000'
                        else:
                            meshpay_token_address = Web3.to_checksum_address(token_address) if token_address else '0x0000000000000000000000000000000000000000'
                        
                        meshpay_balance_wei = self.meshpay_contract.functions.getAccountBalance(
                            address, meshpay_token_address
                        ).call()
                        meshpay_balance = self._wei_to_human(meshpay_balance_wei, decimals)
                        logger.info(f"Successfully got {token_symbol} MeshPay balance: {meshpay_balance}")
                        
                    except Exception as e:
                        logger.error(f"Failed to get {token_symbol} MeshPay balance for {address}: {e}")
                        meshpay_balance = "0"
                else:
                    logger.warning("MeshPay contract not available, using 0 for MeshPay balances")
                    meshpay_balance = "0"
                
                # Calculate total
                total_balance = str(Decimal(wallet_balance) + Decimal(meshpay_balance))
                
                balances.append(TokenBalance(
                    token_symbol=token_symbol,
                    token_address=token_address,
                    wallet_balance=wallet_balance,
                    meshpay_balance=meshpay_balance,
                    total_balance=total_balance,
                    decimals=decimals
                ))
                
            except Exception as e:
                logger.error(f"Failed to process {token_symbol} balance for {address}: {e}")
                # Add zero balance as fallback
                balances.append(TokenBalance(
                    token_symbol=token_symbol,
                    token_address=token_config['address'],
                    wallet_balance="0",
                    meshpay_balance="0",
                    total_balance="0",
                    decimals=token_config['decimals']
                ))
        
        return balances
    
    async def get_contract_stats(self) -> Optional[ContractStats]:
        """Get overall contract statistics."""
        if not self.meshpay_contract:
            logger.error("FastPay contract not initialized")
            return None
        
        try:
            # Get total accounts
            total_accounts = self.meshpay_contract.functions.totalAccounts().call()
            
            # Get total balances for each token
            total_token_balances = {}
            total_native_balance = "0"
            
            for token_symbol, token_config in SUPPORTED_TOKENS.items():
                token_address = Web3.to_checksum_address(token_config['address'])
                total_balance_wei = self.meshpay_contract.functions.totalBalance(token_address).call()
                total_balance = self._wei_to_human(total_balance_wei, token_config['decimals'])
                
                if token_config['is_native']:
                    total_native_balance = total_balance
                else:
                    total_token_balances[token_symbol] = total_balance
            
            return ContractStats(
                total_accounts=total_accounts,
                total_native_balance=total_native_balance,
                total_token_balances=total_token_balances
            )
            
        except Exception as e:
            logger.error(f"Failed to get contract stats: {e}")
            return None
    
    async def is_account_registered(self, address: str) -> bool:
        """Check if an account is registered with FastPay."""
        if not self.meshpay_contract:
            return False
        
        try:
            address = Web3.to_checksum_address(address)
            return self.meshpay_contract.functions.isAccountRegistered(address).call()
        except Exception as e:
            logger.error(f"Failed to check registration for {address}: {e}")
            return False
    
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
            logger.error(f"Failed to get {event_name} events: {e}")
            return []
    
    def _wei_to_human(self, wei_amount: int, decimals: int) -> str:
        """Convert wei amount to human-readable format."""
        return str(Decimal(wei_amount) / Decimal(10 ** decimals))
    
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
                    total_accounts = self.meshpay_contract.functions.totalAccounts().call()
                    health_status['meshpay_contract'] = True
                    health_status['total_accounts'] = total_accounts
                    
        except Exception as e:
            health_status['error'] = str(e)
            logger.error(f"Blockchain health check failed: {e}")
        
        return health_status

# Global blockchain client instance
blockchain_client = BlockchainClient() 