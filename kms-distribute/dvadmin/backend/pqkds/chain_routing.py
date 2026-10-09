"""节点初始化仍能完成，但不能把 DID 待绑定包装成旧合约上传成功。

Fabric 公钥绑定由登记事务的 outbox 驱动；这里不再从物化列拼旧合约入参，
也不把 IP/端口、设备身份或私钥传到外部 DID metadata。
"""


class FabricBindingUploadStatus:
    def upload_node_registration(self, node):
        return {
            'success': False,
            'provider': 'FABRIC_DID',
            'code': 'FABRIC_BINDING_ASYNC',
            'message': '公钥绑定由 Fabric DID 登记任务处理；未配置或未确认不表示上链成功',
        }
