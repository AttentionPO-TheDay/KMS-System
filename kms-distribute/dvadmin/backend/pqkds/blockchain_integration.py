from web3 import Web3
from web3.middleware import geth_poa_middleware
import json
import hashlib
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from .falcon_crypto import FalconCertificateLessKDS
logger = logging.getLogger(__name__)
class BlockchainKDS:
    def __init__(self, 
                 provider_url: str = "http://localhost:8545",
                 contract_address: Optional[str] = None,
                 private_key: Optional[str] = None):
        self.w3 = Web3(Web3.HTTPProvider(provider_url))
        try:
            if not self.w3.is_connected():
                logger.warning("Failed to connect to blockchain node")
            else:
                self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
        except Exception as e:
            logger.warning(f"Blockchain connection check failed: {e}")
        self.contract_address = contract_address
        self.private_key = private_key
        self.account = None
        if private_key and private_key.strip():
            try:
                if not private_key.startswith('0x'):
                    private_key = '0x' + private_key
                self.account = self.w3.eth.account.from_key(private_key)
            except Exception as e:
                logger.warning(f"Invalid private key format: {e}")
                self.account = None
        self.falcon_kds = FalconCertificateLessKDS()
        self.contract_abi = [
            {
                "inputs": [
                    {"name": "userId", "type": "string"},
                    {"name": "publicKeyHash", "type": "bytes32"},
                    {"name": "keyData", "type": "string"}
                ],
                "name": "storePublicKey",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [{"name": "userId", "type": "string"}],
                "name": "getPublicKey",
                "outputs": [
                    {"name": "publicKeyHash", "type": "bytes32"},
                    {"name": "keyData", "type": "string"},
                    {"name": "timestamp", "type": "uint256"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"name": "userId", "type": "string"},
                    {"name": "newKeyData", "type": "string"}
                ],
                "name": "updatePublicKey",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "userId", "type": "string"},
                    {"indexed": False, "name": "publicKeyHash", "type": "bytes32"},
                    {"indexed": False, "name": "timestamp", "type": "uint256"}
                ],
                "name": "PublicKeyStored",
                "type": "event"
            }
        ]
        self.contract = None
        if contract_address and self.w3.isConnected():
            self.contract = self.w3.eth.contract(
                address=contract_address,
                abi=self.contract_abi
            )
    def setup_system(self) -> Dict[str, Any]:
        system_params = self.falcon_kds.setup()
        try:
            if self.w3.is_connected() and self.contract and self.account:
                try:
                    self._store_system_params_on_chain(system_params)
                except Exception as e:
                    logger.error(f"Failed to store system params on blockchain: {e}")
        except Exception:
            pass
        return system_params
    def register_user_with_blockchain(self, user_id: str) -> Dict[str, Any]:
        user_data = self.falcon_kds.register_user(user_id)
        public_key_data = {
            'user_id': user_id,
            'public_key': user_data['keys']['public_key'],
            'algorithm': 'Falcon-512',
            'timestamp': datetime.now().isoformat(),
            'key_type': 'certificate_less'
        }
        try:
            if self.w3.is_connected() and self.contract and self.account:
                try:
                    tx_hash = self._store_public_key_on_chain(user_id, public_key_data)
                    user_data['blockchain_tx'] = tx_hash
                except Exception as e:
                    logger.error(f"Failed to store public key on blockchain: {e}")
                    user_data['blockchain_error'] = str(e)
        except Exception:
            user_data['blockchain_error'] = 'Blockchain not connected'
        return user_data
    def _store_public_key_on_chain(self, user_id: str, key_data: Dict[str, Any]) -> str:
        if not self.contract or not self.account:
            raise ValueError("Contract or account not initialized")
        key_json = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode()).digest()
        transaction = self.contract.functions.storePublicKey(
            user_id,
            key_hash,
            key_json
        ).buildTransaction({
            'from': self.account.address,
            'gas': 500000,
            'gasPrice': self.w3.toWei('20', 'gwei'),
            'nonce': self.w3.eth.getTransactionCount(self.account.address)
        })
        signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)
        tx_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
        receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
        return receipt.transactionHash.hex()
    def _store_system_params_on_chain(self, params: Dict[str, Any]):
        logger.info(f"System parameters: {params}")
    def get_public_key_from_blockchain(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.contract:
            return None
        try:
            result = self.contract.functions.getPublicKey(user_id).call()
            key_hash, key_data, timestamp = result
            if key_data:
                return {
                    'key_data': json.loads(key_data),
                    'key_hash': key_hash.hex(),
                    'timestamp': timestamp
                }
        except Exception as e:
            logger.error(f"Failed to retrieve public key from blockchain: {e}")
        return None
    def verify_key_integrity(self, user_id: str) -> bool:
        try:
            local_public_key = self.falcon_kds.get_user_public_key(user_id)
        except ValueError:
            return False
        blockchain_data = self.get_public_key_from_blockchain(user_id)
        if not blockchain_data:
            return False
        blockchain_key = blockchain_data['key_data']['public_key']
        return local_public_key.tolist() == blockchain_key
    def update_user_key(self, user_id: str) -> Dict[str, Any]:
        user_data = self.register_user_with_blockchain(user_id)
        if self.w3.isConnected() and self.contract and self.account:
            try:
                public_key_data = {
                    'user_id': user_id,
                    'public_key': user_data['keys']['public_key'],
                    'algorithm': 'Falcon-512',
                    'timestamp': datetime.now().isoformat(),
                    'key_type': 'certificate_less_updated'
                }
                key_json = json.dumps(public_key_data, sort_keys=True)
                transaction = self.contract.functions.updatePublicKey(
                    user_id,
                    key_json
                ).buildTransaction({
                    'from': self.account.address,
                    'gas': 300000,
                    'gasPrice': self.w3.toWei('20', 'gwei'),
                    'nonce': self.w3.eth.getTransactionCount(self.account.address)
                })
                signed_txn = self.w3.eth.account.sign_transaction(transaction, self.private_key)
                tx_hash = self.w3.eth.sendRawTransaction(signed_txn.rawTransaction)
                receipt = self.w3.eth.waitForTransactionReceipt(tx_hash)
                user_data['update_tx'] = receipt.transactionHash.hex()
            except Exception as e:
                logger.error(f"Failed to update key on blockchain: {e}")
                user_data['blockchain_error'] = str(e)
        return user_data
    def get_blockchain_status(self) -> Dict[str, Any]:
        try:
            if not self.w3.is_connected():
                return {
                    'connected': False,
                    'error': 'Not connected to blockchain node'
                }
            latest_block = self.w3.eth.block_number
            return {
                'connected': True,
                'latest_block': latest_block,
                'account': self.account.address if self.account else None,
                'contract_address': self.contract_address
            }
        except Exception as e:
            return {
                'connected': False,
                'error': str(e)
            }
    def get_user_keys_local(self, user_id: str) -> Optional[Dict[str, Any]]:
        if user_id in self.falcon_kds.users:
            return self.falcon_kds.users[user_id].get_keys()
        return None