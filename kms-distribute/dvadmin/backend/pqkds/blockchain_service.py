import json
import logging
import os
import base64
from typing import Dict, Any
from web3 import Web3
from eth_account import Account
from .models import BlockchainConfig, Node, Transaction, Block
try:
    import solcx
except Exception:
    solcx = None
logger = logging.getLogger(__name__)
class BlockchainService:
    def __init__(self):
        # 旧构造器会读账户、联 RPC，甚至自动部署合约。必须先判后端，
        # 不能等一次旧链写入之后才发现当前已经选择 Fabric。
        from .chain_backend import require_legacy_backend
        require_legacy_backend('初始化旧 Web3 区块链服务')
        self.w3 = None
        self.contract = None
        self.account = None
        self.account_address = None
        self._use_local_signer = False
        self.config = None
        self._initialize()
    def _initialize(self):
        try:
            self.config = (
                BlockchainConfig.objects.filter(is_active=True)
                .order_by('-update_datetime', '-create_datetime', '-id')
                .first()
            )
            if not self.config:
                logger.debug("没有找到活跃的区块链配置")
                return
            self.w3 = Web3(Web3.HTTPProvider(self.config.provider_url))
            selected_address = None
            if getattr(self.config, 'private_key', None):
                try:
                    self.account = Account.from_key(self.config.private_key)
                    selected_address = Web3.to_checksum_address(self.account.address)
                    self.account_address = selected_address
                except Exception as e:
                    logger.warning(f"从配置私钥初始化账户失败，将尝试使用本地节点账户: {e}")
                    self.account = None
            try:
                if self.w3.is_connected():
                    node_accounts = []
                    try:
                        node_accounts = [Web3.to_checksum_address(a) for a in self.w3.eth.accounts]
                    except Exception:
                        node_accounts = []
                    def _get_balance(addr: str) -> int:
                        try:
                            return self.w3.eth.get_balance(addr)
                        except Exception:
                            return 0
                    need_pick_local = False
                    if self.account_address is None:
                        need_pick_local = True
                    else:
                        try:
                            if _get_balance(self.account_address) == 0:
                                need_pick_local = True
                        except Exception:
                            need_pick_local = True
                    if need_pick_local and node_accounts:
                        funded = None
                        for addr in node_accounts:
                            if _get_balance(addr) > 0:
                                funded = addr
                                break
                        if funded:
                            self.account = None
                            self.account_address = funded
                            self._use_local_signer = True
                            self.w3.eth.default_account = funded
                            logger.info(f"已选择本地链上有余额账户用于交易: {funded}")
                        else:
                            if self.account_address is None:
                                raise Exception("区块链节点无可用且有余额的账户，请为节点账户充值或解锁账户")
            except Exception as e:
                logger.warning(f"选择本地账户过程发生问题: {e}")
            if self.config.contract_address and hasattr(self.config, 'contract_abi') and self.config.contract_abi:
                contract_address = Web3.to_checksum_address(self.config.contract_address)
                self.contract = self.w3.eth.contract(
                    address=contract_address,
                    abi=json.loads(self.config.contract_abi)
                )
            logger.info(f"区块链服务初始化成功，连接到 {self.config.provider_url}")
            try:
                self._ensure_contract_ready()
                logger.info("智能合约已准备好")
            except Exception as contract_err:
                logger.warning(f"合约准备失败，稍后再尝试: {contract_err}")
        except Exception as e:
            logger.error(f"区块链服务初始化失败: {e}")
    def _current_from_address(self):
        if self.account_address:
            return Web3.to_checksum_address(self.account_address)
        if self.account is not None:
            return Web3.to_checksum_address(self.account.address)
        raise Exception("未配置有效的账户地址")
    def _next_nonce(self, from_address: str) -> int:
        return self.w3.eth.get_transaction_count(from_address)
    def _send_transaction(self, tx: dict):
        if self._use_local_signer:
            return self.w3.eth.send_transaction(tx)
        if not getattr(self.config, 'private_key', None):
            raise Exception("未提供用于签名的私钥，且本地节点未启用签名")
        signed_txn = self.w3.eth.account.sign_transaction(tx, self.config.private_key)
        return self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    def _reregister_nodes_on_new_contract(self):
        try:
            from .models import Node
            nodes = Node.objects.all()
            for node in nodes:
                try:
                    result = self.register_node_on_blockchain(
                        node.node_id,
                        node.name,
                        node.ip_address,
                        node.port
                    )
                    if result['success']:
                        logger.info(f"节点 {node.node_id} 在新合约中注册成功")
                        if node.kyber_public_key:
                            try:
                                kyber_pk_bytes = base64.b64decode(node.kyber_public_key)
                                upload_result = self.upload_kyber_public_key(node.node_id, kyber_pk_bytes)
                                if upload_result['success']:
                                    logger.info(f"节点 {node.node_id} Kyber公钥在新合约中上传成功")
                                else:
                                    logger.warning(f"节点 {node.node_id} Kyber公钥上传失败: {upload_result.get('error')}")
                            except Exception as e:
                                logger.warning(f"节点 {node.node_id} Kyber公钥上传异常: {e}")
                    else:
                        logger.warning(f"节点 {node.node_id} 在新合约中注册失败: {result.get('error')}")
                except Exception as e:
                    logger.warning(f"节点 {node.node_id} 在新合约中注册异常: {e}")
        except Exception as e:
            logger.warning(f"重新注册节点时发生异常: {e}")
    def _ensure_contract_ready(self):
        if not self.is_connected():
            raise Exception("未连接到区块链网络")
        if self.contract is not None:
            try:
                _ = self.contract.functions.getNodeCount().call()
                return
            except Exception:
                logger.warning("检测到现有合约不可用或版本不匹配，将重新部署")
        result = self.compile_and_deploy_contract()
        if not result.get('success'):
            raise Exception(f"合约部署失败: {result.get('error')}")
        contract_address = Web3.to_checksum_address(result['contract_address'])
        abi = json.loads(self.config.contract_abi)
        self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
    @staticmethod
    def _static_contract_abi() -> list:
        return [
            {"inputs": [], "name": "getNodeCount", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "string", "name": "nodeId", "type": "string"}], "name": "nodeList", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "name": "nodeIds", "outputs": [{"internalType": "string", "name": "", "type": "string"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "string", "name": "nodeId", "type": "string"}], "name": "getNodeInfo", "outputs": [
                {"internalType": "string", "name": "name", "type": "string"},
                {"internalType": "string", "name": "ipAddress", "type": "string"},
                {"internalType": "uint256", "name": "port", "type": "uint256"},
                {"internalType": "bytes", "name": "kyberPublicKey", "type": "bytes"},
                {"internalType": "bytes", "name": "falconPublicKey", "type": "bytes"},
                {"internalType": "bool", "name": "isActive", "type": "bool"},
                {"internalType": "uint256", "name": "registrationTime", "type": "uint256"},
                {"internalType": "uint256", "name": "lastUpdateTime", "type": "uint256"}
            ], "stateMutability": "view", "type": "function"},
            {"inputs": [], "name": "getAllNodes", "outputs": [{"internalType": "string[]", "name": "", "type": "string[]"}], "stateMutability": "view", "type": "function"},
            {"inputs": [{"internalType": "string", "name": "", "type": "string"}], "name": "nodes", "outputs": [
                {"internalType": "string", "name": "nodeId", "type": "string"},
                {"internalType": "string", "name": "name", "type": "string"},
                {"internalType": "string", "name": "kyberPublicKey", "type": "string"},
                {"internalType": "string", "name": "falconPublicKey", "type": "string"},
                {"internalType": "bool", "name": "isActive", "type": "bool"},
                {"internalType": "uint256", "name": "timestamp", "type": "uint256"}
            ], "stateMutability": "view", "type": "function"}
        ]
    def is_connected(self):
        try:
            return self.w3 and self.w3.is_connected()
        except:
            return False
    def get_latest_block(self):
        if not self.is_connected():
            return None
        try:
            return self.w3.eth.get_block('latest')
        except Exception as e:
            logger.error(f"获取最新区块失败: {e}")
            return None
    def _compile_contract(self):
        sol_path = os.path.join(os.path.dirname(__file__), 'contracts', 'FalconKDS.sol')
        if not os.path.exists(sol_path):
            raise Exception(f"找不到合约文件: {sol_path}")
        if solcx is None:
            raise Exception("缺少 py-solc-x 依赖，请安装后重试: pip install py-solc-x")
        target_version = '0.8.20'
        installed = [str(v) for v in getattr(solcx, 'get_installed_solc_versions', lambda: [])()]
        try:
            if target_version not in installed:
                solcx.install_solc(target_version)
            solcx.set_solc_version(target_version)
        except Exception as install_err:
            import platform
            import zipfile
            import io
            import stat
            import requests
            system = platform.system().lower()
            arch = platform.machine().lower()
            base_dir = os.path.join(os.path.dirname(__file__), 'contracts', 'solc-bin', target_version)
            os.makedirs(base_dir, exist_ok=True)
            if 'windows' in system:
                asset = f"windows-amd64/solc-windows-amd64-v{target_version}+commit.a1b79de6.zip"
                binary_name = 'solc.exe'
            elif 'linux' in system:
                asset = f"linux-amd64/solc-linux-amd64-v{target_version}+commit.a1b79de6.zip"
                binary_name = 'solc'
            elif 'darwin' in system or 'mac' in system:
                asset = f"macosx-amd64/solc-macosx-amd64-v{target_version}+commit.a1b79de6.zip"
                binary_name = 'solc'
            else:
                raise Exception(f"不支持的平台: {system}")
            urls = [
                f"https://binaries.soliditylang.org/{asset}",
                f"https://github.com/ethereum/solc-bin/raw/gh-pages/{asset}",
            ]
            resp = None
            for u in urls:
                try:
                    resp = requests.get(u, timeout=30, verify=False)
                    if resp.status_code == 200:
                        break
                except Exception:
                    resp = None
            if not resp or resp.status_code != 200:
                raise Exception(f"下载 solc 失败: {install_err}")
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            member = [m for m in zf.namelist() if m.endswith(binary_name)][0]
            out_path = os.path.join(base_dir, binary_name)
            with open(out_path, 'wb') as f:
                f.write(zf.read(member))
            try:
                os.chmod(out_path, os.stat(out_path).st_mode | stat.S_IEXEC)
            except Exception:
                pass
            solcx.set_solc_binary(out_path)
        with open(sol_path, 'r', encoding='utf-8') as f:
            source = f.read()
        compiled = solcx.compile_source(
            source,
            output_values=['abi', 'bin'],
            optimize=True
        )
        if not compiled:
            raise Exception("Solidity 编译未产生输出")
        _, contract_interface = next(iter(compiled.items()))
        return contract_interface
    def compile_and_deploy_contract(self):
        try:
            if not self.is_connected():
                raise Exception("未连接到区块链网络")
            from_address = self._current_from_address()
            balance = self.w3.eth.get_balance(from_address)
            balance_eth = self.w3.from_wei(balance, 'ether')
            logger.info(f"当前账户 {from_address} 余额: {balance_eth} ETH")
            if balance == 0:
                raise Exception("账户余额为0，无法部署合约。请为所选账户充值或在本地区块链上使用有余额账户")
            logger.info("编译FalconKDS合约...")
            contract_interface = self._compile_contract()
            logger.info("合约编译完成")
            contract = self.w3.eth.contract(
                abi=contract_interface['abi'],
                bytecode=contract_interface['bin']
            )
            estimated_gas = contract.constructor().estimate_gas({'from': from_address})
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('1', 'gwei')))
            transaction = contract.constructor().build_transaction({
                'from': from_address,
                'nonce': self._next_nonce(from_address),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                self.config.contract_address = tx_receipt.contractAddress
                self.config.contract_abi = json.dumps(contract_interface['abi'])
                self.config.save()
                self.contract = self.w3.eth.contract(
                    address=tx_receipt.contractAddress,
                    abi=contract_interface['abi']
                )
                logger.info(f"合约部署成功，地址: {tx_receipt.contractAddress}")
                logger.info("开始重新注册节点到新合约...")
                self._reregister_nodes_on_new_contract()
                return {
                    'success': True,
                    'contract_address': tx_receipt.contractAddress,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed
                }
            else:
                raise Exception("合约部署失败")
        except Exception as e:
            logger.warning(f"合约部署失败: {e}")
            try:
                if self.config and self.config.contract_address:
                    contract_address = Web3.to_checksum_address(self.config.contract_address)
                    abi = None
                    if getattr(self.config, 'contract_abi', None):
                        try:
                            abi = json.loads(self.config.contract_abi)
                        except Exception:
                            abi = None
                    if abi is None:
                        abi = self._static_contract_abi()
                    temp_contract = self.w3.eth.contract(address=contract_address, abi=abi)
                    _ = temp_contract.functions.getNodeCount().call()
                    self.contract = temp_contract
                    logger.info(f"使用已存在的合约地址: {contract_address}")
                    return {
                        'success': True,
                        'contract_address': contract_address,
                        'tx_hash': '',
                        'gas_used': 0,
                    }
            except Exception as verify_err:
                logger.error(f"已存在合约验证失败: {verify_err}")
            return {
                'success': False,
                'error': str(e)
            }
    def register_node_on_blockchain(self, node_id, name, ip_address, port):
        try:
            if not self.contract:
                raise Exception("智能合约未部署")
            from_address = self._current_from_address()
            fn = self.contract.functions.registerNode(node_id, name, ip_address, port)
            estimated_gas = fn.estimate_gas({'from': from_address})
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            transaction = fn.build_transaction({
                'from': from_address,
                'nonce': self._next_nonce(from_address),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                logger.info(f"节点 {node_id} 在区块链上注册成功")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed
                }
            else:
                raise Exception("节点注册交易失败")
        except Exception as e:
            logger.error(f"节点区块链注册失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def upload_kyber_public_key(self, node_id, kyber_public_key):
        try:
            if not self.contract:
                logger.warning("智能合约未部署，跳过Kyber公钥上传")
                return {
                    'success': True,
                    'message': '智能合约未部署，跳过区块链上传',
                    'skipped': True
                }
            if isinstance(kyber_public_key, str):
                try:
                    kyber_public_key_bytes = base64.b64decode(kyber_public_key)
                    logger.info(f"检测到Base64编码的Kyber公钥，已解码，长度: {len(kyber_public_key_bytes)}")
                except Exception:
                    kyber_public_key_bytes = kyber_public_key.encode('utf-8')
            else:
                kyber_public_key_bytes = kyber_public_key
            logger.info(f"上传节点 {node_id} Kyber公钥，长度: {len(kyber_public_key_bytes)} bytes")
            from_address = self._current_from_address()
            fn = self.contract.functions.uploadKyberPublicKey(node_id, kyber_public_key_bytes)
            estimated_gas = fn.estimate_gas({'from': from_address})
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            transaction = fn.build_transaction({
                'from': from_address,
                'nonce': self._next_nonce(from_address),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                logger.info(f"节点 {node_id} Kyber公钥上传成功")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed
                }
            else:
                raise Exception("Kyber公钥上传交易失败")
        except Exception as e:
            logger.error(f"Kyber公钥上传失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def upload_falcon_public_key(self, node_id, falcon_public_key):
        try:
            if not self.contract:
                logger.warning("智能合约未部署，跳过Falcon公钥上传")
                return {
                    'success': True,
                    'message': '智能合约未部署，跳过区块链上传',
                    'skipped': True
                }
            if isinstance(falcon_public_key, str):
                falcon_public_key_bytes = falcon_public_key.encode('utf-8')
            else:
                falcon_public_key_bytes = falcon_public_key
            key_size_mb = len(falcon_public_key_bytes) / (1024 * 1024)
            logger.info(f"Falcon公钥大小: {key_size_mb:.3f}MB")
            if key_size_mb > 1.0:
                logger.info(f" 检测到大型Falcon V2密钥 ({key_size_mb:.3f}MB)，使用哈希值存储")
            else:
                logger.info(f" 检测到标准Falcon V1密钥 ({key_size_mb:.3f}MB)，统一使用哈希值存储")
            logger.info(f"   新策略: 所有Falcon公钥统一使用SHA256哈希值上传到区块链")
            logger.info(f"   优势: 降低Gas消耗，统一验证流程，提高系统一致性")
            return self.upload_falcon_public_key_hash(node_id, falcon_public_key)
        except Exception as e:
            logger.error(f"Falcon公钥上传失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def upload_kyber_public_key_hash(self, node_id: str, kyber_public_key_hash: str) -> Dict[str, Any]:
        try:
            if not self.contract:
                logger.warning("智能合约未部署，跳过Kyber公钥哈希上传")
                return {
                    'success': True,
                    'message': '智能合约未部署，跳过区块链上传',
                    'skipped': True
                }
            logger.info(f" 上传Kyber公钥哈希值: {kyber_public_key_hash[:16]}...")
            from_address = self._current_from_address()
            fn = self.contract.functions.storeKyberHash(node_id, kyber_public_key_hash)
            try:
                estimated_gas = fn.estimate_gas({'from': from_address})
            except Exception as e:
                logger.warning(f"Gas估算失败: {e}，使用默认值")
                estimated_gas = 100_000
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            transaction = fn.build_transaction({
                'from': from_address,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': self._next_nonce(from_address),
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                logger.info(f"节点 {node_id} Kyber公钥哈希上传成功")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed,
                    'public_key_hash': kyber_public_key_hash,
                    'upload_type': 'hash'
                }
            else:
                raise Exception(f"Kyber公钥哈希上传交易失败，状态: {tx_receipt.status}")
        except Exception as e:
            logger.error(f"Kyber公钥哈希上传失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def upload_falcon_public_key_hash(self, node_id: str, falcon_public_key: str) -> Dict[str, Any]:
        try:
            import hashlib
            if isinstance(falcon_public_key, str):
                falcon_public_key_bytes = falcon_public_key.encode('utf-8')
            else:
                falcon_public_key_bytes = falcon_public_key
            public_key_hash = hashlib.sha256(falcon_public_key_bytes).hexdigest()
            logger.info(f" 计算Falcon公钥哈希值: {public_key_hash[:16]}...")
            from_address = self._current_from_address()
            fn = self.contract.functions.storeFalconHash(node_id, public_key_hash)
            try:
                estimated_gas = fn.estimate_gas({'from': from_address})
                logger.info(f"估算Gas: {estimated_gas}")
            except Exception as e:
                logger.warning(f"Gas估算失败: {e}，使用默认值")
                estimated_gas = 200_000
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            logger.info(f"使用Gas限制: {gas_limit}, Gas价格: {gas_price}")
            transaction = fn.build_transaction({
                'from': from_address,
                'gas': gas_limit,
                'gasPrice': gas_price,
                'nonce': self._next_nonce(from_address),
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info(f" 交易收据信息:")
            logger.info(f"   状态: {tx_receipt.status}")
            logger.info(f"   Gas使用: {tx_receipt.gasUsed:,}")
            logger.info(f"   区块号: {tx_receipt.blockNumber}")
            if tx_receipt.status == 1:
                logger.info(f"节点 {node_id} Falcon公钥哈希上传成功")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed,
                    'public_key_hash': public_key_hash,
                    'upload_type': 'hash'
                }
            else:
                logger.error(f" 交易失败，状态: {tx_receipt.status}")
                raise Exception(f"Falcon公钥哈希上传交易失败，状态: {tx_receipt.status}")
        except Exception as e:
            logger.error(f"Falcon公钥哈希上传失败: {e}")
            return {'success': False, 'error': str(e)}
    def get_node_kyber_public_key(self, node_id):
        try:
            self._ensure_contract_ready()
            if not self.contract:
                raise Exception("智能合约未部署")
            kyber_key_raw = self.contract.functions.getKyberPublicKey(node_id).call()
            if isinstance(kyber_key_raw, bytes):
                kyber_key = kyber_key_raw
                try:
                    str_repr = kyber_key.decode('utf-8', errors='strict')
                    if str_repr.startswith('[') and str_repr.endswith(']'):
                        array = json.loads(str_repr)
                        if isinstance(array, list) and len(array) > 0:
                            if all(isinstance(x, int) and 0 <= x <= 255 for x in array):
                                kyber_key = bytes(array)
                                logger.info(f"检测到JSON数组格式的Kyber公钥，已转换，长度: {len(kyber_key)}")
                            else:
                                logger.warning(f"检测到JSON数组格式但元素值超出范围(0-255)，这不是有效的Kyber公钥")
                except (UnicodeDecodeError, ValueError):
                    pass
            elif isinstance(kyber_key_raw, str):
                if kyber_key_raw.startswith('0x'):
                    kyber_key = bytes.fromhex(kyber_key_raw[2:])
                elif kyber_key_raw.startswith('[') and kyber_key_raw.endswith(']'):
                    try:
                        array = json.loads(kyber_key_raw)
                        if isinstance(array, list) and all(isinstance(x, int) and 0 <= x <= 255 for x in array):
                            kyber_key = bytes(array)
                            logger.info(f"检测到JSON数组格式的Kyber公钥，已转换，长度: {len(kyber_key)}")
                        else:
                            logger.warning(f"检测到JSON数组格式但元素值超出范围(0-255)，这不是有效的Kyber公钥")
                            kyber_key = kyber_key_raw.encode()
                    except Exception as json_err:
                        logger.debug(f"JSON解析失败: {json_err}")
                        kyber_key = kyber_key_raw.encode()
                else:
                    try:
                        decoded = base64.b64decode(kyber_key_raw)
                        if len(decoded) in [800, 1632]:
                            logger.info(f"检测到Base64编码的Kyber公钥，解码成功，长度: {len(decoded)}")
                            kyber_key = decoded
                        else:
                            logger.debug(f"Base64解码后长度为{len(decoded)}，不是预期的800或1632，使用原字符串编码")
                            kyber_key = kyber_key_raw.encode()
                    except Exception as base64_err:
                        logger.debug(f"Base64解码失败: {base64_err}，使用原字符串编码")
                        kyber_key = kyber_key_raw.encode()
            elif isinstance(kyber_key_raw, list):
                if all(isinstance(x, int) and 0 <= x <= 255 for x in kyber_key_raw):
                    kyber_key = bytes(kyber_key_raw)
                    logger.info(f"检测到列表格式的Kyber公钥，已转换，长度: {len(kyber_key)}")
                else:
                    logger.warning(f"检测到列表格式但元素值超出范围(0-255)，这不是有效的Kyber公钥")
                    kyber_key = bytes(kyber_key_raw)
            else:
                kyber_key = bytes(kyber_key_raw)
            logger.info(f"从区块链获取节点 {node_id} Kyber公钥，长度: {len(kyber_key)} bytes")
            return {
                'success': True,
                'kyber_public_key': kyber_key
            }
        except Exception as e:
            logger.error(f"获取Kyber公钥失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_node_falcon_public_key(self, node_id):
        try:
            self._ensure_contract_ready()
            if not self.contract:
                raise Exception("智能合约未部署")
            falcon_key = self.contract.functions.getFalconPublicKey(node_id).call()
            return {
                'success': True,
                'falcon_public_key': falcon_key
            }
        except Exception as e:
            logger.error(f"获取Falcon公钥失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_falcon_public_key_hash(self, node_id: str) -> Dict[str, Any]:
        try:
            self._ensure_contract_ready()
            if not self.contract:
                raise Exception("智能合约未部署")
            public_key_hash = self.contract.functions.getFalconHash(node_id).call()
            if public_key_hash and public_key_hash != "0x0000000000000000000000000000000000000000000000000000000000000000":
                logger.info(f" 获取节点 {node_id} Falcon公钥哈希: {public_key_hash[:16]}...")
                return {
                    'success': True,
                    'public_key_hash': public_key_hash,
                    'node_id': node_id
                }
            else:
                logger.warning(f" 节点 {node_id} 的Falcon公钥哈希不存在或为空")
                return {
                    'success': False,
                    'error': f'节点 {node_id} 的Falcon公钥哈希不存在'
                }
        except Exception as e:
            logger.error(f"获取节点 {node_id} Falcon公钥哈希失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def record_session_key_exchange(self, session_id, from_node_id, to_node_id, encrypted_session_key, signature):
        try:
            if not self.contract:
                raise Exception("智能合约未部署")
            if isinstance(encrypted_session_key, str):
                try:
                    import base64
                    encrypted_session_key_bytes = base64.b64decode(encrypted_session_key)
                except:
                    encrypted_session_key_bytes = encrypted_session_key.encode('utf-8')
            else:
                encrypted_session_key_bytes = encrypted_session_key
            if isinstance(signature, str):
                try:
                    import base64
                    signature_bytes = base64.b64decode(signature)
                except:
                    signature_bytes = signature.encode('utf-8')
            else:
                signature_bytes = signature
            logger.info(f" 记录会话密钥交换到区块链: {session_id}")
            logger.info(f"   加密会话密钥大小: {len(encrypted_session_key_bytes)} bytes")
            logger.info(f"   签名大小: {len(signature_bytes)} bytes")
            from_node_id_str = str(from_node_id)
            to_node_id_str = str(to_node_id)
            from_address = self._current_from_address()
            fn = self.contract.functions.recordSessionKeyExchange(
                session_id, from_node_id_str, to_node_id_str, encrypted_session_key_bytes, signature_bytes
            )
            estimated_gas = fn.estimate_gas({'from': from_address})
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            transaction = fn.build_transaction({
                'from': from_address,
                'nonce': self._next_nonce(from_address),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                logger.info(f"会话密钥交换记录成功: {session_id}")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed
                }
            else:
                raise Exception("会话密钥交换记录交易失败")
        except Exception as e:
            logger.error(f"会话密钥交换记录失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def record_message(self, message_id: str, session_id: str,
                       sender_node_id: str, receiver_node_id: str,
                       ciphertext_hash: str, algorithm: str = 'AES-256-GCM') -> Dict[str, Any]:
        """将加密消息记录上链"""
        try:
            if not self.contract:
                logger.warning("智能合约未部署，跳过消息上链")
                return {
                    'success': True,
                    'message': '智能合约未部署，跳过消息上链',
                    'skipped': True
                }
            logger.info(f"记录加密消息到区块链: message_id={message_id}, session={session_id}")
            from_address = self._current_from_address()
            fn = self.contract.functions.recordMessage(
                str(message_id),
                str(session_id),
                str(sender_node_id),
                str(receiver_node_id),
                str(ciphertext_hash),
                str(algorithm)
            )
            estimated_gas = fn.estimate_gas({'from': from_address})
            latest_block = self.w3.eth.get_block('latest')
            block_gas_limit = int(latest_block.get('gasLimit') or latest_block.get('gas_limit') or 30_000_000)
            gas_limit = min(int(estimated_gas * 13 // 10), block_gas_limit - 1)
            gas_price = int(getattr(self.w3.eth, 'gas_price', self.w3.to_wei('20', 'gwei')))
            transaction = fn.build_transaction({
                'from': from_address,
                'nonce': self._next_nonce(from_address),
                'gas': gas_limit,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            tx_hash = self._send_transaction(transaction)
            tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if tx_receipt.status == 1:
                logger.info(f"消息 {message_id} 上链成功")
                return {
                    'success': True,
                    'tx_hash': tx_hash.hex() if hasattr(tx_hash, 'hex') else Web3.to_hex(tx_hash),
                    'gas_used': tx_receipt.gasUsed,
                    'message_id': message_id
                }
            else:
                raise Exception("消息上链交易失败")
        except Exception as e:
            logger.error(f"消息上链失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_all_nodes_from_blockchain(self):
        try:
            logger.info("【获取区块链节点】开始执行get_all_nodes_from_blockchain")
            try:
                logger.info("【获取区块链节点】尝试确保合约可用")
                self._ensure_contract_ready()
                logger.info("【获取区块链节点】合约已准备就绪")
            except Exception as ensure_err:
                logger.warning(f"【获取区块链节点】确保合约可用失败: {ensure_err}，将尝试使用静态 ABI 访问已有合约")
                if not self.config or not self.config.contract_address:
                    logger.error("【获取区块链节点】没有活跃配置或合约地址，无法继续")
                    raise
                try:
                    contract_address = Web3.to_checksum_address(self.config.contract_address)
                    logger.info(f"【获取区块链节点】使用合约地址: {contract_address}")
                    abi = None
                    if getattr(self.config, 'contract_abi', None):
                        try:
                            abi = json.loads(self.config.contract_abi)
                            logger.info("【获取区块链节点】使用配置中的ABI")
                        except Exception as abi_err:
                            logger.warning(f"【获取区块链节点】解析配置ABI失败: {abi_err}，使用静态ABI")
                            abi = None
                    if abi is None:
                        abi = self._static_contract_abi()
                        logger.info("【获取区块链节点】使用静态ABI")
                    self.contract = self.w3.eth.contract(address=contract_address, abi=abi)
                    logger.info("【获取区块链节点】合约对象创建成功")
                except Exception as contract_err:
                    logger.error(f"【获取区块链节点】创建合约对象失败: {contract_err}")
                    raise
            logger.info("【获取区块链节点】调用getAllNodes()")
            node_ids = self.contract.functions.getAllNodes().call()
            logger.info(f"【获取区块链节点】从区块链getAllNodes()获取到 {len(node_ids)} 个节点ID")

            # 获取数据库中存在的节点ID
            from pqkds.models import Node
            db_node_ids = set(Node.objects.values_list('node_id', flat=True))
            logger.info(f"【获取区块链节点】数据库中存在 {len(db_node_ids)} 个节点")

            # 过滤出数据库中存在的节点
            valid_node_ids = [nid for nid in node_ids if nid in db_node_ids]
            logger.info(f"【获取区块链节点】过滤后有效节点数: {len(valid_node_ids)} 个（已删除节点: {len(node_ids) - len(valid_node_ids)} 个）")

            nodes_info = []
            def _safe_decode_data(data, field_name=""):
                if data is None:
                    return ""
                try:
                    if field_name in ['node_id', 'name', 'ip_address']:
                        if isinstance(data, str):
                            return data
                        elif isinstance(data, (bytes, bytearray)):
                            try:
                                return data.decode('utf-8')
                            except:
                                return data.decode('latin-1', errors='ignore')
                        elif hasattr(data, 'hex'):
                            try:
                                return bytes.fromhex(data.hex()).decode('utf-8')
                            except:
                                return data.hex()
                        else:
                            return str(data)
                    if isinstance(data, (bytes, bytearray)):
                        import base64
                        return base64.b64encode(data).decode('utf-8')
                    elif hasattr(data, 'hex'):
                        import base64
                        hex_str = data.hex()
                        return base64.b64encode(bytes.fromhex(hex_str)).decode('utf-8')
                    elif isinstance(data, str):
                        if not data or data == '':
                            return ""
                        if data.startswith('0x'):
                            import base64
                            hex_data = data[2:]
                            if hex_data:
                                if len(hex_data) % 2 != 0:
                                    hex_data = '0' + hex_data
                                return base64.b64encode(bytes.fromhex(hex_data)).decode('utf-8')
                        return data
                    else:
                        return str(data) if data else ""
                except Exception as e:
                    logger.warning(f"处理区块链数据失败 ({field_name}): {e}, 数据类型: {type(data)}")
                    return ""

            # 只处理有效的节点
            for node_id in valid_node_ids:
                try:
                    info = self.contract.functions.getNodeInfo(node_id).call()
                    falcon_public_key_hash = ""
                    try:
                        falcon_public_key_hash = self.contract.functions.getFalconHash(node_id).call()
                    except Exception as e:
                        logger.warning(f"获取节点 {node_id} 的Falcon公钥哈希失败: {e}")
                    nodes_info.append({
                        'node_id': _safe_decode_data(node_id, "node_id"),
                        'name': _safe_decode_data(info[0], "name"),
                        'ip_address': _safe_decode_data(info[1], "ip_address"),
                        'port': int(info[2]) if info[2] is not None else 0,
                        'kyber_public_key': _safe_decode_data(info[3], "kyber_public_key"),
                        'falcon_public_key': _safe_decode_data(info[4], "falcon_public_key"),
                        'falcon_public_key_hash': falcon_public_key_hash,
                        'is_active': bool(info[5]),
                        'registration_time': int(info[6]) if info[6] is not None else 0,
                        'last_update_time': int(info[7]) if info[7] is not None else 0,
                    })
                except Exception as e:
                    logger.error(f"读取链上节点 {node_id} 信息失败: {e}")

            if len(valid_node_ids) == 0:
                logger.info("区块链中没有有效节点（所有节点都已从数据库删除），返回空列表")
            logger.info(f"最终返回 {len(nodes_info)} 个有效节点")
            return {
                'success': True,
                'nodes': nodes_info
            }
        except Exception as e:
            logger.error(f"【获取区块链节点】获取节点列表失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    def _repair_blockchain_node_list(self, node_ids_to_add):
        try:
            if not self.contract:
                logger.warning("合约未初始化，无法修复nodeList")
                return False
            logger.info(f"开始修复区块链nodeList，需要处理 {len(node_ids_to_add)} 个节点")
            repaired_count = 0
            for node_id in node_ids_to_add:
                try:
                    try:
                        node_exists = self.contract.functions.nodeExists(node_id).call()
                    except Exception:
                        node_exists = False
                    if not node_exists:
                        try:
                            db_node = Node.objects.filter(node_id=node_id).first()
                            if db_node:
                                tx_hash = self.contract.functions.registerNode(
                                    node_id,
                                    db_node.name or node_id,
                                    str(db_node.ip_address) if db_node.ip_address else '127.0.0.1',
                                    db_node.port or 0
                                ).transact({
                                    'from': self.account_address or self.account.address
                                })
                                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                                logger.info(f" 已注册节点 {node_id} 到区块链")
                                repaired_count += 1
                            else:
                                logger.warning(f"数据库中找不到节点 {node_id}，跳过")
                                continue
                        except Exception as reg_err:
                            logger.warning(f"注册节点 {node_id} 到区块链失败: {reg_err}")
                            continue
                    else:
                        if hasattr(self.contract.functions, 'syncNodeList'):
                            try:
                                tx_hash = self.contract.functions.syncNodeList(node_id).transact({
                                    'from': self.account_address or self.account.address
                                })
                                self.w3.eth.wait_for_transaction_receipt(tx_hash)
                                logger.info(f" 已同步节点 {node_id} 到nodeList")
                                repaired_count += 1
                            except Exception as sync_err:
                                logger.debug(f"同步节点 {node_id} 到nodeList: {sync_err}")
                except Exception as node_err:
                    logger.warning(f"处理节点 {node_id} 时出错: {node_err}")
                    continue
            logger.info(f"修复完成，成功处理 {repaired_count} 个节点")
            return repaired_count > 0
        except Exception as e:
            logger.error(f"修复区块链nodeList失败: {e}")
            return False
    def get_node_info_from_blockchain(self, node_id: str) -> Dict[str, Any]:
        try:
            if not self.contract:
                raise Exception("智能合约未部署")
            logger.info(f"从区块链查询节点 {node_id} 的信息")
            try:
                node_exists = self.contract.functions.nodeExists(node_id).call()
                if not node_exists:
                    logger.warning(f"节点 {node_id} 在区块链上不存在")
                    return {
                        'success': False,
                        'error': f'节点 {node_id} 不存在'
                    }
            except Exception as e:
                logger.error(f"检查节点存在性失败: {e}")
                return {
                    'success': False,
                    'error': f'检查节点存在性失败: {str(e)}'
                }
            try:
                info = self.contract.functions.getNodeInfo(node_id).call()
                def _safe_decode_data(data, field_name=""):
                    if data is None:
                        return ""
                    if isinstance(data, bytes):
                        try:
                            return data.decode('utf-8').rstrip('\x00')
                        except Exception:
                            hex_data = data.hex()
                            if len(hex_data) % 2 != 0:
                                hex_data = '0' + hex_data
                            return base64.b64encode(bytes.fromhex(hex_data)).decode('utf-8')
                    else:
                        return str(data) if data else ""
                falcon_public_key_hash = ""
                try:
                    falcon_public_key_hash = self.contract.functions.getFalconHash(node_id).call()
                    if falcon_public_key_hash:
                        logger.info(f"获取节点 {node_id} 的Falcon公钥哈希: {falcon_public_key_hash[:32]}...")
                except Exception as e:
                    logger.warning(f"获取Falcon公钥哈希失败: {e}")
                node_info = {
                    'success': True,
                    'node_id': node_id,
                    'name': _safe_decode_data(info[0], "name"),
                    'ip_address': _safe_decode_data(info[1], "ip_address"),
                    'port': int(info[2]) if info[2] is not None else 0,
                    'kyber_public_key': _safe_decode_data(info[3], "kyber_public_key"),
                    'falcon_public_key': _safe_decode_data(info[4], "falcon_public_key"),
                    'falcon_public_key_hash': falcon_public_key_hash,
                    'is_active': bool(info[5]),
                    'registration_time': int(info[6]) if info[6] is not None else 0,
                    'last_update_time': int(info[7]) if info[7] is not None else 0,
                }
                logger.info(f"成功从区块链获取节点 {node_id} 的信息")
                return node_info
            except Exception as e:
                logger.error(f"获取节点 {node_id} 信息失败: {e}")
                return {
                    'success': False,
                    'error': f'获取节点信息失败: {str(e)}'
                }
        except Exception as e:
            logger.error(f"从区块链获取节点 {node_id} 信息异常: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def get_blockchain_status(self):
        try:
            if not self.is_connected():
                return {
                    'success': False,
                    'error': '未连接到区块链网络'
                }
            latest_block = self.get_latest_block()
            node_count = 0
            account_balance = 0
            if self.account_address:
                try:
                    balance_wei = self.w3.eth.get_balance(self.account_address)
                    account_balance = self.w3.from_wei(balance_wei, 'ether')
                except Exception as e:
                    logger.error(f"获取账户余额失败: {e}")
            if self.contract:
                try:
                    node_count = self.contract.functions.getNodeCount().call()
                except:
                    pass
            return {
                'success': True,
                'network_id': self.w3.eth.chain_id,
                'latest_block_number': latest_block['number'] if latest_block else 0,
                'latest_block_hash': latest_block['hash'].hex() if latest_block else '',
                'contract_address': self.config.contract_address if self.config else '',
                'account_address': self.account_address or (self.account.address if self.account else ''),
                'account_balance': float(account_balance),
                'node_count': node_count,
                'is_connected': True
            }
        except Exception as e:
            logger.error(f"获取区块链状态失败: {e}")
            return {
                'success': False,
                'error': str(e)
            }