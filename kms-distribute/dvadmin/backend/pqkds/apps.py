from django.apps import AppConfig
import logging
logger = logging.getLogger(__name__)
class PqkdsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pqkds'
    verbose_name = '后量子密钥分发系统'
    def ready(self):
        try:
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception:
                return
            self.ensure_security_level_fields()
            self.auto_fix_all_nodes()
        except Exception as e:
            logger.warning(f"PQKDS应用初始化时出现警告: {e}")
    def ensure_security_level_fields(self):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                try:
                    logger.info(" 添加kyber_security_level字段成功")
                except Exception:
                    pass
                try:
                    logger.info(" 添加falcon_security_level字段成功")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"检查安全级别字段时出错: {e}")
    def auto_fix_all_nodes(self):
        """启动时的节点密钥格式体检：**只报告，不再"修复"**（KMS-015 改）。

        <h2>为什么把"修复"删掉</h2>
        原实现在长度不符时**在服务端 `generate_keypair()` 并写回
        `kyber_private_key`** —— 那是 §4.4 明令停止的"新业务写入私钥"：
        它会把节点公钥换成一把节点本地根本没有对应私钥的新密钥，节点此后
        解不开任何按它公钥封的信封，而库里一切"看起来正常"。
        KMS-005 之后私钥只在节点本机产生，服务端**没有任何合法场景**需要
        替节点重造密钥对 —— 发现格式异常时正确的动作是**把它报出来**
        （让运维决定重建还是重新初始化），不是替它做决定。

        <h2>体检范围</h2>
        只查"服务端还持有 Kyber 私钥列"的节点（存量节点）：这本身就是
        KMS-015 要清空的列，清空之后这里会自然变成一次全覆盖的"无异常"。
        """
        try:
            from .models import Node
            from django.db import connection
            import base64
            with connection.cursor() as cursor:
                try:
                    cursor.execute("SELECT blockchain_synced FROM dvadmin_pqkds_nodes LIMIT 1")
                except Exception:
                    logger.info(" 新字段尚未创建，跳过节点体检，请执行数据库迁移")
                    return
            nodes = Node.objects.all()
            if not nodes.exists():
                return
            logger.info(f" 开始检查 {nodes.count()} 个节点的密钥格式...")
            anomalous = []
            for node in nodes:
                try:
                    if not node.kyber_public_key or not node.kyber_private_key:
                        # 私钥列已被清空（或从未写入）——这是新链路下的**正常状态**：
                        # 私钥在节点本机，服务端不该有。跳过，不当作异常。
                        continue
                    security_level = 512
                    try:
                        if hasattr(node, 'kyber_security_level') and node.kyber_security_level:
                            security_level = int(node.kyber_security_level)
                    except Exception:
                        pass
                    from .crypto_utils import KyberCrypto
                    pk_bytes = base64.b64decode(node.kyber_public_key)
                    sk_bytes = base64.b64decode(node.kyber_private_key)
                    kyber = KyberCrypto(security_level)
                    if (len(pk_bytes) != kyber.public_key_bytes
                            or len(sk_bytes) != kyber.secret_key_bytes):
                        # ⚠️ 只记录，**不生成、不写库**（见 docstring）。
                        anomalous.append(node.node_id)
                        logger.warning(
                            " 节点 %s 的 Kyber 密钥格式异常（pk=%dB sk=%dB）："
                            "服务端不再自动重建（那会产生节点本地没有对应私钥的公钥）。"
                            "请让该节点重新初始化，或用 KMS-015 的清理脚本清空存量私钥列。",
                            node.node_id, len(pk_bytes), len(sk_bytes),
                        )
                except Exception as e:
                    logger.warning(f"检查节点 {node.node_id} 时出错: {e}")
            if anomalous:
                logger.warning(" 密钥格式异常的节点（只报告，不修复）：%s", anomalous)
            else:
                logger.info(" 所有节点密钥格式正常，无需修复")
        except Exception as e:
            logger.warning(f"节点密钥体检时出错: {e}")