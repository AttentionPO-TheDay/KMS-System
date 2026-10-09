"""业务初始化与链写入独立；暂停不实例化旧 SDK、不编造上链成功。"""


class PausedChainUploadStatus:
    def upload_node_registration(self, node):
        from .chain_backend import get_chain_backend
        return {
            'success': False, 'provider': get_chain_backend(),
            'code': 'CHAIN_WRITES_PAUSED', 'status': 'PAUSED',
            'message': '真实上链已暂停，公钥与操作审计仅保留本地',
        }


class FabricBindingUploadStatus:
    def upload_node_registration(self, node):
        return {
            'success': False,
            'provider': 'FABRIC_DID',
            'code': 'FABRIC_BINDING_ASYNC',
            'message': '公钥绑定由 Fabric DID 登记任务处理；未配置或未确认不表示上链成功',
        }
