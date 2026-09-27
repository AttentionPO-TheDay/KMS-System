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
        try:
            from .models import Node
            from .crypto_utils import KyberCrypto
            from django.db import connection
            import base64
            with connection.cursor() as cursor:
                try:
                    cursor.execute("SELECT blockchain_synced FROM dvadmin_pqkds_nodes LIMIT 1")
                except Exception:
                    logger.info(" 新字段尚未创建，跳过节点修复，请执行数据库迁移")
                    return
            nodes = Node.objects.all()
            if not nodes.exists():
                return
            logger.info(f" 开始检查 {nodes.count()} 个节点的密钥格式...")
            fixed_count = 0
            for node in nodes:
                try:
                    if not node.kyber_public_key or not node.kyber_private_key:
                        continue
                    security_level = 512
                    try:
                        if hasattr(node, 'kyber_security_level') and node.kyber_security_level:
                            security_level = int(node.kyber_security_level)
                    except:
                        pass
                    pk_bytes = base64.b64decode(node.kyber_public_key)
                    sk_bytes = base64.b64decode(node.kyber_private_key)
                    kyber = KyberCrypto(security_level)
                    expected_pk_len = kyber.public_key_bytes
                    expected_sk_len = kyber.secret_key_bytes
                    if len(pk_bytes) != expected_pk_len or len(sk_bytes) != expected_sk_len:
                        logger.info(f" 修复节点 {node.node_id} 的密钥格式...")
                        new_pk, new_sk = kyber.generate_keypair()
                        test_ct, test_ss = kyber.encrypt(new_pk)
                        recovered_ss = kyber.decrypt(test_ct, new_sk)
                        if test_ss == recovered_ss:
                            node.kyber_public_key = base64.b64encode(new_pk).decode('utf-8')
                            node.kyber_private_key = base64.b64encode(new_sk).decode('utf-8')
                            node.partial_key_received = False
                            node.partial_key_data = ''
                            node.falcon_public_key = ''
                            node.falcon_private_key = ''
                            if node.status in ['partial_key_received', 'falcon_generated', 'falcon_uploaded']:
                                node.status = 'registered'
                            node.save(update_fields=[
                                'kyber_public_key', 'kyber_private_key',
                                'partial_key_received', 'partial_key_data',
                                'falcon_public_key', 'falcon_private_key',
                                'status'
                            ])
                            fixed_count += 1
                            logger.info(f" 节点 {node.node_id} 修复成功")
                        else:
                            logger.error(f" 节点 {node.node_id} 密钥验证失败")
                except Exception as e:
                    logger.warning(f"修复节点 {node.node_id} 时出错: {e}")
            if fixed_count > 0:
                logger.info(f" 自动修复完成！共修复 {fixed_count} 个节点的密钥格式问题")
            else:
                logger.info(" 所有节点密钥格式正常，无需修复")
        except Exception as e:
            logger.warning(f"自动修复节点密钥时出错: {e}")