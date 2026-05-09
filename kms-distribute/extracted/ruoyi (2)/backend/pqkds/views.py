import logging
from rest_framework import status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Count, Q, Max
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta
from dvadmin.utils.viewset import CustomModelViewSet
from dvadmin.utils.json_response import DetailResponse, SuccessResponse, ErrorResponse
from .models import (
    SystemParameters, Node, Block, Transaction,
    SessionKey, Message, BlockchainConfig,
    FalconKeyPair, KeyDistributionLog
)
from .serializers import (
    SystemParametersSerializer, NodeSerializer, NodeCreateSerializer, NodeDetailSerializer, NodeUpdateSerializer,
    BlockSerializer, TransactionSerializer, SessionKeySerializer, SessionKeyCreateSerializer,
    MessageSerializer, MessageCreateSerializer, BlockchainConfigSerializer, BlockchainConfigCreateSerializer,
    FalconKeyPairSerializer, FalconKeyPairDetailSerializer, KeyDistributionLogSerializer,
    SystemStatsSerializer, NodeStatsSerializer, BlockchainStatsSerializer,
    NodeRegistrationResponseSerializer, KeyGenerationResponseSerializer,
    SessionKeyExchangeResponseSerializer
)
from .kgc_service import KGCService
from .node_service import NodeService
from .blockchain_service import BlockchainService
from .database_blockchain_sync_service import DatabaseToBlockchainSyncService
from .session_key_expiration_service import SessionKeyExpirationService
from .key_negotiation_service import KeyNegotiationService
from .public_key_retrieval_service import PublicKeyRetrievalService
from .node_discovery_service import NodeDiscoveryService
from .operation_log import set_request_msg
logger = logging.getLogger(__name__)
class SystemParametersViewSet(CustomModelViewSet):
    queryset = SystemParameters.objects.all()
    serializer_class = SystemParametersSerializer
    @action(detail=False, methods=['post'])
    def initialize(self, request):
        try:
            set_request_msg(request, '系统参数初始化')
            kgc = KGCService()
            name = request.data.get('name', 'default_system')
            result = kgc.initialize_system(name)
            return SuccessResponse(data=result, msg="系统参数初始化成功")
        except Exception as e:
            return ErrorResponse(msg=f"系统参数初始化失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def active(self, request):
        try:
            params = SystemParameters.objects.filter(is_active=True).first()
            if params:
                serializer = self.get_serializer(params)
                return SuccessResponse(data=serializer.data, msg="获取活跃系统参数成功")
            else:
                return ErrorResponse(msg="没有找到活跃的系统参数")
        except Exception as e:
            return ErrorResponse(msg=f"获取系统参数失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def generate_kyber_partial_key(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            set_request_msg(request, f'KGC生成Kyber部分私钥(节点{node_id})')
            logger.info(f"KGC开始为节点{node_id}生成Kyber部分私钥")
            kgc = KGCService()
            result = kgc.generate_and_save_kyber_partial_key(node_id)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"KGC生成Kyber部分私钥异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"生成失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def generate_falcon_partial_key(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            set_request_msg(request, f'KGC生成Falcon部分私钥(节点{node_id})')
            logger.info(f"KGC开始为节点{node_id}生成Falcon部分私钥")
            kgc = KGCService()
            result = kgc.generate_and_save_falcon_partial_key(node_id)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"KGC生成Falcon部分私钥异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"生成失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def generate_all_partial_keys(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            set_request_msg(request, f'KGC生成所有部分私钥(节点{node_id})')
            logger.info(f"KGC开始为节点{node_id}生成所有部分私钥")
            kgc = KGCService()
            result = kgc.generate_all_partial_keys_for_node(node_id)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"KGC生成所有部分私钥异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"生成失败: {str(e)}")
class NodeViewSet(CustomModelViewSet):
    queryset = Node.objects.none()
    serializer_class = NodeSerializer
    extra_filter_class = []
    def get_object(self):
        lookup_url_kwarg = self.lookup_url_kwarg or self.lookup_field
        lookup_value = self.kwargs.get(lookup_url_kwarg)
        if lookup_value is None:
            return super().get_object()
        try:
            return Node.objects.get(node_id=lookup_value)
        except Node.DoesNotExist:
            pass
        try:
            return Node.objects.get(pk=lookup_value)
        except Node.DoesNotExist:
            pass
        from django.http import Http404
        raise Http404("Node not found")
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'stats', 'register', 'generate_falcon_keys', 'generate_falcon_keys_v2', 'generate_falcon_keypair', 'keys', 'key_details', 'destroy', 'batch_delete', 'update_keys', 'update', 'partial_update', 'get_public_keys', 'discover_node', 'prepare_key_negotiation']:
            return []
        return super().get_permissions()
    def get_serializer_class(self):
        if self.action == 'create':
            return NodeCreateSerializer
        elif self.action in ['retrieve', 'list']:
            return NodeDetailSerializer
        elif self.action in ['update', 'partial_update']:
            return NodeUpdateSerializer
        return NodeSerializer
    def get_queryset(self):
        try:
            if getattr(self, 'action', None) == 'list':
                active_blockchain_config = (
                    BlockchainConfig.objects.filter(is_active=True)
                    .order_by('-update_datetime', '-create_datetime', '-id')
                    .first()
                )
                if active_blockchain_config:
                    logger.info(f"使用活跃区块链配置: {active_blockchain_config.name}")
                    try:
                        blockchain_service = BlockchainService()
                        result = blockchain_service.get_all_nodes_from_blockchain()
                        if result.get('success'):
                            nodes = result.get('nodes', [])
                            node_ids = []
                            logger.info(f" 从区块链获取到 {len(nodes)} 个节点")
                            import base64
                            for item in nodes:
                                node_id = item.get('node_id')
                                if not node_id:
                                    continue
                                node_ids.append(node_id)
                                try:
                                    node_obj = Node.objects.filter(node_id=node_id).first()
                                    kyber_val = item.get('kyber_public_key')
                                    falcon_val = item.get('falcon_public_key')
                                    def _to_b64(v):
                                        if v is None:
                                            return ''
                                        try:
                                            if isinstance(v, (bytes, bytearray)):
                                                return base64.b64encode(v).decode('utf-8')
                                            if hasattr(v, 'hex'):
                                                hex_str = v.hex()
                                                return base64.b64encode(bytes.fromhex(hex_str)).decode('utf-8')
                                            if isinstance(v, str):
                                                if v.startswith('0x'):
                                                    hex_data = v[2:]
                                                    if len(hex_data) % 2 != 0:
                                                        hex_data = '0' + hex_data
                                                    return base64.b64encode(bytes.fromhex(hex_data)).decode('utf-8')
                                                else:
                                                    try:
                                                        return base64.b64encode(v.encode('utf-8')).decode('utf-8')
                                                    except UnicodeEncodeError:
                                                        return base64.b64encode(v.encode('latin-1')).decode('utf-8')
                                            if hasattr(v, '__str__'):
                                                str_v = str(v)
                                                return base64.b64encode(str_v.encode('utf-8')).decode('utf-8')
                                        except Exception as e:
                                            logger.warning(f"转换公钥数据为base64失败: {e}, 数据类型: {type(v)}, 数据: {repr(v)}")
                                            return ''
                                        return ''
                                    kyber_b64 = _to_b64(kyber_val)
                                    falcon_b64 = _to_b64(falcon_val)
                                    if node_obj:
                                        update_fields = []
                                        name = item.get('name')
                                        ip = item.get('ip_address')
                                        port = item.get('port')
                                        if node_obj.blockchain_config != active_blockchain_config:
                                            node_obj.blockchain_config = active_blockchain_config
                                            update_fields.append('blockchain_config')
                                        if name and node_obj.name != name:
                                            node_obj.name = name
                                            update_fields.append('name')
                                        if ip and str(node_obj.ip_address) != str(ip):
                                            node_obj.ip_address = ip
                                            update_fields.append('ip_address')
                                        if port and node_obj.port != int(port):
                                            node_obj.port = int(port)
                                            update_fields.append('port')
                                        if kyber_b64 and node_obj.kyber_public_key != kyber_b64:
                                            node_obj.kyber_public_key = kyber_b64
                                            update_fields.append('kyber_public_key')
                                        if falcon_b64 and node_obj.falcon_public_key != falcon_b64:
                                            node_obj.falcon_public_key = falcon_b64
                                            update_fields.append('falcon_public_key')
                                        if update_fields:
                                            node_obj.save(update_fields=update_fields)
                                        logger.info(f"   更新了节点 {node_id}")
                                    else:
                                        Node.objects.create(
                                            node_id=node_id,
                                            name=item.get('name') or node_id,
                                            ip_address=item.get('ip_address') or '127.0.0.1',
                                            port=int(item.get('port') or 0),
                                            kyber_public_key=kyber_b64,
                                            falcon_public_key=falcon_b64,
                                            status='kyber_uploaded' if kyber_b64 else 'registered',
                                            blockchain_config=active_blockchain_config,
                                        )
                                        logger.info(f"   创建了节点 {node_id}")
                                except Exception as e:
                                    logger.warning(f"同步节点 {node_id} 失败: {e}")
                                    pass
                            logger.info(f" 共处理了 {len(node_ids)} 个区块链节点")
                            if node_ids:
                                result_nodes = Node.objects.filter(
                                    node_id__in=node_ids,
                                    blockchain_config=active_blockchain_config
                                )
                                logger.info(f"   返回 {result_nodes.count()} 个节点")
                                return result_nodes
                            else:
                                logger.warning(" 区块链节点列表为空")
                                return Node.objects.filter(blockchain_config=active_blockchain_config)
                        else:
                            logger.warning("区块链调用失败，显示当前活跃配置下的本地节点")
                    except Exception as e:
                        logger.warning(f"区块链服务异常: {e}，显示当前活跃配置下的本地节点")
                    filtered_nodes = Node.objects.filter(blockchain_config=active_blockchain_config)
                    logger.info(f" 强制过滤结果: {filtered_nodes.count()} 个节点属于配置 '{active_blockchain_config.name}'")
                    return filtered_nodes
                else:
                    logger.warning("没有活跃的区块链配置，返回空结果")
                    return Node.objects.none()
        except Exception as e:
            logger.warning(f"获取节点列表异常: {e}，尝试显示活跃配置下的节点")
            try:
                active_config = BlockchainConfig.objects.filter(is_active=True).first()
                if active_config:
                    return Node.objects.filter(blockchain_config=active_config)
                else:
                    return Node.objects.none()
            except Exception:
                return Node.objects.none()
        return Node.objects.all()
    def list(self, request, *args, **kwargs):
        logger.info(" 开始处理节点列表请求")
        active_config = self._get_current_active_blockchain_config()
        if active_config:
            logger.info(f" 使用活跃配置: {active_config.name} (ID: {active_config.id})")
            from django.db.models import Q
            base_queryset = Node.objects.filter(
                Q(blockchain_config=active_config) | Q(blockchain_config__isnull=True)
            )
            config_msg = f"当前区块链: {active_config.name}"
        else:
            logger.warning(" 没有活跃的区块链配置，显示所有节点")
            base_queryset = Node.objects.all()
            config_msg = "（未配置区块链，显示所有节点）"
        filtered_queryset = self._apply_search_filters(base_queryset, request.query_params)
        ordered_queryset = filtered_queryset.order_by('-create_datetime')
        page = int(request.query_params.get('page', 1))
        limit = int(request.query_params.get('limit', 10))
        total = ordered_queryset.count()
        start = (page - 1) * limit
        end = start + limit
        nodes = ordered_queryset[start:end]
        serializer = self.get_serializer(nodes, many=True)
        logger.info(f" 成功返回 {len(serializer.data)} 个节点 (第{page}页，总计{total}个) - {config_msg}")
        return Response({
            'code': 2000,
            'data': serializer.data,
            'total': total,
            'msg': f' 获取节点列表成功 - {config_msg} ({total}个节点)'
        })
    def _get_current_active_blockchain_config(self):
        try:
            active_configs = BlockchainConfig.objects.filter(is_active=True)
            if active_configs.count() > 1:
                logger.warning(f" 发现 {active_configs.count()} 个活跃配置，自动修复为唯一配置")
                latest_config = active_configs.order_by('-update_datetime', '-create_datetime', '-id').first()
                other_configs = BlockchainConfig.objects.exclude(id=latest_config.id)
                updated_count = other_configs.update(is_active=False)
                logger.info(f" 已将 '{latest_config.name}' 设为唯一活跃配置，禁用了 {updated_count} 个其他配置")
                return latest_config
            elif active_configs.count() == 1:
                return active_configs.first()
            else:
                logger.warning(" 没有找到活跃的区块链配置")
                return None
        except Exception as e:
            logger.error(f" 获取活跃区块链配置失败: {e}")
            return None
    def _apply_search_filters(self, queryset, query_params):
        try:
            node_id = query_params.get('node_id', '').strip()
            if node_id:
                queryset = queryset.filter(node_id__icontains=node_id)
                logger.info(f" 按节点ID过滤: {node_id}")
            name = query_params.get('name', '').strip()
            if name:
                queryset = queryset.filter(name__icontains=name)
                logger.info(f" 按节点名称过滤: {name}")
            status = query_params.get('status', '').strip()
            if status:
                queryset = queryset.filter(status=status)
                logger.info(f" 按节点状态过滤: {status}")
            return queryset
        except Exception as e:
            logger.warning(f" 应用搜索过滤失败: {e}")
            return queryset
    @action(detail=False, methods=['post'])
    def register(self, request):
        try:
            set_request_msg(request, f'注册节点({request.data.get("node_id", "")})')
            logger.info(f" 收到节点注册请求，数据: {request.data}")
            node_id = request.data.get('node_id')
            ip_address = request.data.get('ip_address')
            port = request.data.get('port')
            if node_id and Node.objects.filter(node_id=node_id).exists():
                existing_node = Node.objects.get(node_id=node_id)
                logger.warning(f" 节点ID {node_id} 已存在")
                return SuccessResponse(
                    data={
                        'node_id': existing_node.node_id,
                        'name': existing_node.name,
                        'ip_address': existing_node.ip_address,
                        'port': existing_node.port,
                        'status': existing_node.status,
                        'create_datetime': existing_node.create_datetime,
                        'is_duplicate': True
                    },
                    msg=f"该节点已注册（节点名称: {existing_node.name}，状态: {existing_node.get_status_display()}）"
                )
            if ip_address and port and Node.objects.filter(ip_address=ip_address, port=port).exists():
                existing_node = Node.objects.filter(ip_address=ip_address, port=port).first()
                logger.warning(f" IP地址 {ip_address}:{port} 已被节点 {existing_node.name} 使用")
                return SuccessResponse(
                    data={
                        'node_id': existing_node.node_id,
                        'name': existing_node.name,
                        'ip_address': existing_node.ip_address,
                        'port': existing_node.port,
                        'status': existing_node.status,
                        'create_datetime': existing_node.create_datetime,
                        'is_duplicate': True
                    },
                    msg=f"IP地址和端口已被使用（节点名称: {existing_node.name}，状态: {existing_node.get_status_display()}）"
                )
            serializer = NodeCreateSerializer(data=request.data)
            if serializer.is_valid():
                logger.info(f" 序列化器验证通过")
                node_data = serializer.validated_data
                node_service = NodeService(node_data['node_id'])
                basic_fields = ['name', 'ip_address', 'port']
                basic_data = {field: node_data[field] for field in basic_fields}
                optional_fields = ['phone', 'email', 'contact_person', 'organization',
                                 'department', 'location', 'node_type', 'hardware_spec',
                                 'description', 'tags', 'kyber_security_level', 'falcon_security_level']
                optional_data = {field: node_data.get(field) for field in optional_fields if field in node_data}
                logger.info(f" 开始调用node_service.register_node")
                result = node_service.register_node(**basic_data, **optional_data)
                if result['success']:
                    logger.info(f" 节点注册成功: {node_data['node_id']}")
                    return SuccessResponse(data={
                        'node_id': result.get('node_id'),
                        'status': result.get('status'),
                        'message': result.get('message'),
                        'kyber_keygen_time': result.get('kyber_keygen_time'),
                        'kyber_keygen_duration': result.get('kyber_keygen_duration')
                    }, msg="节点注册成功")
                else:
                    logger.error(f" 节点注册失败: {result['message']}")
                    return ErrorResponse(msg=result['message'])
            else:
                errors = serializer.errors
                error_messages = []
                for field, error_list in errors.items():
                    for error in error_list:
                        error_messages.append(f"{field}: {error}")
                main_message = error_messages[0] if error_messages else "数据验证失败"
                logger.error(f" 序列化器验证失败: {main_message}, 详细错误: {errors}")
                return ErrorResponse(msg=main_message, data=errors)
        except Exception as e:
            logger.error(f" 节点注册异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"节点注册失败: {str(e)}")

    @action(detail=True, methods=['post'])
    def generate_falcon_keypair(self, request, pk=None):
        try:
            node = self.get_object()
            set_request_msg(request, f'生成Falcon密钥对(节点{node.node_id})')
            logger.info(f"节点 {node.node_id} 调用generate_falcon_keypair方法")
            logger.info(f"流程：为已注册的节点生成Falcon无证书密钥对")
            from .node_service import NodeService
            node_service = NodeService(node.node_id)
            result = node_service.generate_falcon_keypair()
            if result['success']:
                logger.info(f"节点 {node.node_id} 无证书Falcon密钥对生成成功")
                return SuccessResponse(
                    data={
                        'node_id': node.node_id,
                        'message': result.get('message'),
                        'status': result.get('status'),
                        'kyber_keygen_time': result.get('kyber_keygen_time'),
                        'kyber_keygen_duration': result.get('kyber_keygen_duration'),
                        'falcon_keygen_time': result.get('falcon_keygen_time'),
                        'falcon_keygen_duration': result.get('falcon_keygen_duration')
                    },
                    msg=f"无证书Falcon密钥对生成成功"
                )
            else:
                logger.error(f"节点 {node.node_id} Falcon密钥对生成失败: {result.get('message')}")
                return ErrorResponse(msg=result.get('message', 'Falcon密钥对生成失败'))
        except Exception as e:
            logger.error(f"Falcon密钥对生成异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"Falcon密钥对生成失败: {str(e)}")

    @action(detail=True, methods=['post'])
    def generate_falcon_keys(self, request, pk=None):
        try:
            node = self.get_object()
            set_request_msg(request, f'生成Falcon密钥(节点{node.node_id})')
            logger.info(f"节点 {node.node_id} 调用generate_falcon_keys方法")
            logger.info(f"流程：生成无证书Falcon密钥对")
            from .node_service import NodeService
            node_service = NodeService(node.node_id)
            result = node_service.generate_falcon_keys_v2()
            if result['success']:
                logger.info(f"节点 {node.node_id} 无证书Falcon密钥对生成成功")
                return SuccessResponse(
                    data={
                        'node_id': result.get('node_id'),
                        'message': result.get('message'),
                        'falcon_keygen_duration': result.get('falcon_keygen_duration'),
                        'falcon_keygen_time': result.get('falcon_keygen_time'),
                        'kyber_keygen_duration': result.get('kyber_keygen_duration'),
                        'kyber_keygen_time': result.get('kyber_keygen_time'),
                        'status': result.get('status')
                    },
                    msg=f"无证书Falcon密钥对生成成功"
                )
            else:
                logger.error(f"节点 {node.node_id} Falcon密钥对生成失败: {result.get('message')}")
                return ErrorResponse(msg=result.get('message', 'Falcon密钥对生成失败'))
        except Exception as e:
            logger.error(f"Falcon密钥生成异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"Falcon密钥生成失败: {str(e)}")
    @action(detail=True, methods=['post'])
    def generate_falcon_keys_v2(self, request, pk=None):
        try:
            node = self.get_object()
            set_request_msg(request, f'生成Falcon V2密钥(节点{node.node_id})')
            logger.info(f"节点 {node.node_id} 调用generate_falcon_keys_v2方法")
            logger.info(f"流程：生成无证书Falcon密钥对 (V2)")
            from .node_service import NodeService
            node_service = NodeService(node.node_id)
            result = node_service.generate_falcon_keys_v2()
            if result['success']:
                logger.info(f"节点 {node.node_id} 无证书Falcon V2密钥对生成成功")
                return SuccessResponse(
                    data={
                        'node_id': node.node_id,
                        'algorithm': result.get('algorithm'),
                        'message': result.get('message'),
                        'blockchain_tx_hash': result.get('blockchain_tx_hash'),
                        'timing_info': result.get('timing_info'),
                        'scheme': 'v2',
                        'scheme_name': 'V2(无证书方案)',
                        'falcon_keygen_duration': result.get('falcon_keygen_duration'),
                        'falcon_keygen_time': result.get('falcon_keygen_time'),
                        'kyber_keygen_duration': result.get('kyber_keygen_duration'),
                        'kyber_keygen_time': result.get('kyber_keygen_time')
                    },
                    msg=f"无证书Falcon V2密钥对生成成功"
                )
            else:
                logger.error(f"节点 {node.node_id} Falcon V2密钥对生成失败: {result.get('message')}")
                return ErrorResponse(msg=result.get('message', 'Falcon V2密钥对生成失败'))
        except Exception as e:
            logger.error(f"Falcon V2密钥生成异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"Falcon V2密钥生成失败: {str(e)}")
    @action(detail=True, methods=['post'])
    def update_keys(self, request, pk=None):
        try:
            node = self.get_object()
            data = request.data
            key_type = data.get('key_type')
            set_request_msg(request, f'更新密钥(节点{node.node_id}, 类型:{key_type})')
            security_level = data.get('security_level', 512)
            kyber_security_level = data.get('kyber_security_level', security_level)
            falcon_security_level = data.get('falcon_security_level', security_level)
            falcon_version = 'v2'
            if data.get('falcon_version') == 'v1':
                logger.info("V1方案已弃用，自动切换到V2无证书方案")
            if not key_type or key_type not in ['kyber', 'falcon', 'both']:
                return ErrorResponse(msg="无效的密钥类型，必须是 'kyber', 'falcon' 或 'both'")
            kyber_valid_levels = [512, 768, 1024]
            falcon_valid_levels = [512, 768, 1024]
            if key_type in ['kyber', 'both'] and kyber_security_level not in kyber_valid_levels:
                return ErrorResponse(msg=f"无效的Kyber安全级别，必须是 {kyber_valid_levels} 之一")
            if key_type in ['falcon', 'both'] and falcon_security_level not in falcon_valid_levels:
                return ErrorResponse(msg=f"无效的Falcon安全级别，必须是 {falcon_valid_levels} 之一")
            logger.info(f" 开始更新节点 {node.node_id} 的无证书密钥")
            logger.info(f"   更新类型: {key_type}")
            logger.info(f"   Kyber级别: {kyber_security_level}, Falcon级别: {falcon_security_level}")
            node_service = NodeService(node.node_id)
            if key_type == 'kyber':
                logger.info(f"   执行: 仅更新无证书Kyber密钥...")
                result = node_service.update_kyber_keys(kyber_security_level)
            elif key_type == 'falcon':
                logger.info(f"   执行: 仅更新无证书Falcon V2密钥...")
                result = node_service.update_falcon_keys(falcon_security_level, falcon_version)
            elif key_type == 'both':
                logger.info(f"   执行: 同时更新无证书Kyber和Falcon密钥...")
                result = node_service.update_both_keys(kyber_security_level, falcon_security_level, falcon_version)
            if result['success']:
                # 密钥更新成功后，标记所有相关会话为失效
                from .session_invalidation_service import SessionInvalidationService
                invalidation_result = SessionInvalidationService.invalidate_sessions_for_node_key_update(
                    node,
                    reason='node_key_updated'
                )

                response_data = {
                    'node_id': node.node_id,
                    'key_type': key_type,
                    'update_type': 'certificateless',
                    **result.get('data', {}),
                    'session_invalidation': {
                        'invalidated_count': invalidation_result.get('invalidated_count', 0),
                        'message': invalidation_result.get('message', '')
                    }
                }
                logger.info(f" 密钥更新成功: {result['message']}")
                logger.info(f" 会话失效处理: {invalidation_result['message']}")
                return SuccessResponse(data=response_data, msg=result['message'])
            else:
                logger.error(f" 密钥更新失败: {result['message']}")
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f" 密钥更新异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"密钥更新失败: {str(e)}")
    @action(detail=True, methods=['get'])
    def keys(self, request, pk=None):
        try:
            node = self.get_object()
            from .certificateless_key_update_service import decompress_key_data
            kyber_public_key = decompress_key_data(node.kyber_public_key) if node.kyber_public_key else node.kyber_public_key
            falcon_public_key = decompress_key_data(node.falcon_public_key) if node.falcon_public_key else node.falcon_public_key
            data = {
                'node_id': node.node_id,
                'kyber_public_key': kyber_public_key,
                'falcon_public_key': falcon_public_key,
                'partial_key_received': node.partial_key_received,
                'status': node.status
            }
            return SuccessResponse(data=data, msg="获取节点密钥信息成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取节点密钥信息失败: {str(e)}")
    @action(detail=True, methods=['get'])
    def key_details(self, request, pk=None):
        try:
            node = self.get_object()
            import json
            from .node_service import decompress_key_data

            # 处理Kyber部分私钥信息
            kyber_partial_key_info = None
            if node.kyber_partial_key_data:
                try:
                    kyber_partial_data = json.loads(node.kyber_partial_key_data)
                    kyber_partial_key_info = {
                        'has_data': True,
                        'encrypted_data': node.kyber_partial_key_data,
                        'algorithm': kyber_partial_data.get('algorithm', 'Kyber'),
                        'scheme': kyber_partial_data.get('scheme', 'Shamir(2,3)'),
                        'kgc_share': kyber_partial_data.get('kgc_share', ''),
                        'kgc_share_hash': kyber_partial_data.get('kgc_share_hash', ''),
                        'node_shares_count': kyber_partial_data.get('node_shares_count', 0),
                        'node_shares': kyber_partial_data.get('node_shares', []),
                        'kgc_signature': kyber_partial_data.get('kgc_signature', ''),
                        'timestamp': kyber_partial_data.get('timestamp', ''),
                        'note': 'Shamir秘密分享方案生成的部分私钥'
                    }
                except Exception as e:
                    logger.warning(f"解析Kyber部分私钥数据失败: {e}")
                    kyber_partial_key_info = {
                        'has_data': True,
                        'encrypted_data': node.kyber_partial_key_data,
                        'note': '部分私钥数据格式'
                    }
            else:
                kyber_partial_key_info = {
                    'has_data': False,
                    'encrypted_data': None,
                    'note': '暂无Kyber部分私钥数据'
                }

            # 处理Falcon部分私钥信息
            falcon_partial_key_info = None
            if node.falcon_partial_key_data:
                try:
                    falcon_partial_data = json.loads(node.falcon_partial_key_data)
                    # 提取partial_key字段（base64编码的数据）
                    partial_key_b64 = falcon_partial_data.get('partial_key', '')
                    partial_key_display = partial_key_b64[:200] + '...' if len(partial_key_b64) > 200 else partial_key_b64

                    # 构建Falcon部分私钥信息，包含所有可能的字段
                    falcon_partial_key_info = {
                        'has_data': True,
                        'node_id': falcon_partial_data.get('node_id', ''),
                        'algorithm': falcon_partial_data.get('algorithm', 'CertificatelessFalconOptimized'),
                        'encrypted_data': partial_key_display,
                        'timestamp': falcon_partial_data.get('timestamp', ''),
                        'parameters': falcon_partial_data.get('parameters', {}),
                        'scheme': falcon_partial_data.get('scheme', 'Shamir(2,3)'),
                        'kgc_share': falcon_partial_data.get('kgc_share', ''),
                        'kgc_share_hash': falcon_partial_data.get('kgc_share_hash', ''),
                        'node_shares_count': falcon_partial_data.get('node_shares_count', 0),
                        'node_shares': falcon_partial_data.get('node_shares', []),
                        'kgc_signature': falcon_partial_data.get('kgc_signature', ''),
                        'D_id': falcon_partial_data.get('D_id', ''),
                        'S_id': falcon_partial_data.get('S_id', ''),
                        'H_id': falcon_partial_data.get('H_id', ''),
                        'note': 'Shamir秘密分享方案生成的部分私钥'
                    }
                except Exception as e:
                    logger.warning(f"解析Falcon部分私钥数据失败: {e}")
                    # 即使解析失败，也返回原始数据
                    falcon_partial_key_info = {
                        'has_data': True,
                        'encrypted_data': node.falcon_partial_key_data[:200] + '...' if len(node.falcon_partial_key_data) > 200 else node.falcon_partial_key_data,
                        'note': '部分私钥数据（解析失败，显示原始数据）'
                    }
            elif node.partial_key_data:
                try:
                    partial_data = json.loads(node.partial_key_data)
                    # 检查是否包含falcon_partial_key字段
                    falcon_partial_key = partial_data.get('falcon_partial_key', {})
                    if falcon_partial_key:
                        falcon_partial_key_info = {
                            'has_data': True,
                            'encrypted_data': json.dumps(falcon_partial_key)[:200] + '...' if len(json.dumps(falcon_partial_key)) > 200 else json.dumps(falcon_partial_key),
                            'algorithm': falcon_partial_key.get('algorithm', 'CertificatelessFalcon'),
                            'timestamp': falcon_partial_key.get('timestamp', ''),
                            'note': '使用旧版存储格式'
                        }
                    else:
                        falcon_partial_key_info = {
                            'has_data': False,
                            'encrypted_data': None,
                            'note': '暂无Falcon部分私钥数据'
                        }
                except Exception as e:
                    logger.warning(f"解析旧版部分私钥数据失败: {e}")
                    falcon_partial_key_info = {
                        'has_data': False,
                        'encrypted_data': None,
                        'note': '旧版部分私钥数据（解析失败）'
                    }
            else:
                falcon_partial_key_info = {
                    'has_data': False,
                    'encrypted_data': None,
                    'note': '暂无Falcon部分私钥数据'
                }

            # 计算总体状态
            overall_status = self._calculate_overall_status(node)

            # 构建返回数据
            data = {
                'node_id': node.node_id,
                'kyber': {
                    'public_key': decompress_key_data(node.kyber_public_key) if node.kyber_public_key else None,
                    'private_key': decompress_key_data(node.kyber_private_key) if node.kyber_private_key else None,
                    'partial_key': kyber_partial_key_info,
                    'security_level': node.kyber_security_level if node.kyber_security_level else '512',
                    'keygen_duration': node.kyber_keygen_duration,
                    'keygen_time': node.kyber_keygen_time.isoformat() if node.kyber_keygen_time else None
                },
                'falcon': {
                    'public_key': decompress_key_data(node.falcon_public_key) if node.falcon_public_key else None,
                    'private_key': decompress_key_data(node.falcon_private_key) if node.falcon_private_key else None,
                    'partial_key': falcon_partial_key_info,
                    'security_level': node.falcon_security_level if node.falcon_security_level else '512',
                    'keygen_duration': node.falcon_keygen_duration,
                    'keygen_time': node.falcon_keygen_time.isoformat() if node.falcon_keygen_time else None
                },
                'partial_key_received': node.partial_key_received,
                'status': node.status,
                'overall_status': overall_status
            }
            return SuccessResponse(data=data, msg="获取节点密钥详情成功")
        except Exception as e:
            logger.error(f"获取节点密钥详情失败: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"获取节点密钥详情失败: {str(e)}")

    def _calculate_overall_status(self, node):
        """
        计算节点的总体状态
        返回更详细的状态描述
        """
        status_map = {
            'registered': '已注册',
            'kyber_uploaded': 'Kyber公钥已上传',
            'partial_key_received': '部分私钥已接收',
            'falcon_generated': 'Falcon密钥已生成',
            'active': '活跃',
            'inactive': '非活跃'
        }

        # 构建详细的状态信息
        status_details = {
            'current_status': status_map.get(node.status, node.status),
            'kyber_key_generated': bool(node.kyber_public_key),
            'falcon_key_generated': bool(node.falcon_public_key),
            'kyber_partial_key_received': bool(node.kyber_partial_key_data),
            'falcon_partial_key_received': bool(node.falcon_partial_key_data),
            'partial_key_received': node.partial_key_received,
            'kyber_keygen_duration': node.kyber_keygen_duration,
            'falcon_keygen_duration': node.falcon_keygen_duration
        }

        # 计算进度百分比
        progress = 0
        if node.kyber_public_key:
            progress += 25
        if node.falcon_public_key:
            progress += 25
        if node.kyber_partial_key_data or node.partial_key_data:
            progress += 25
        if node.falcon_partial_key_data or node.partial_key_data:
            progress += 25

        status_details['progress'] = progress

        return status_details


    def stats(self, request):
        try:
            nodes = Node.objects.all()
            stats_data = []
            for node in nodes:
                stats_data.append({
                    'node_id': node.node_id,
                    'name': node.name,
                    'status': node.status,
                    'kyber_key_generated': bool(node.kyber_public_key),
                    'falcon_key_generated': bool(node.falcon_public_key),
                    'partial_key_received': node.partial_key_received,
                    'sessions_count': node.sessions_as_node1.count() + node.sessions_as_node2.count(),
                    'messages_sent': node.sent_messages.count(),
                    'messages_received': node.received_messages.count()
                })
            return SuccessResponse(data=stats_data, msg="获取节点统计信息成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取节点统计信息失败: {str(e)}")
    @action(detail=True, methods=['get'])
    def get_public_keys(self, request, pk=None):
        try:
            target_node_id = pk
            logger.info(f"获取节点 {target_node_id} 的公钥")
            public_key_service = PublicKeyRetrievalService()
            result = public_key_service.get_node_public_keys(target_node_id)
            if result.get('success'):
                return SuccessResponse(data={
                    'node_id': target_node_id,
                    'kyber_public_key': result.get('kyber_public_key'),
                    'falcon_public_key': result.get('falcon_public_key'),
                    'source': result.get('source')
                }, msg="获取公钥成功")
            else:
                return ErrorResponse(msg=result.get('error', '获取公钥失败'))
        except Exception as e:
            logger.error(f"获取节点公钥异常: {e}")
            return ErrorResponse(msg=f"获取公钥失败: {str(e)}")
    @action(detail=True, methods=['get'])
    def discover_node(self, request, pk=None):
        try:
            target_node_id = pk
            logger.info(f"发现节点 {target_node_id} 的网络地址")
            node_discovery = NodeDiscoveryService()
            result = node_discovery.discover_node(target_node_id)
            if result.get('success'):
                node_info = result.get('node_info', {})
                return SuccessResponse(data={
                    'node_id': target_node_id,
                    'ip_address': node_info.get('ip_address'),
                    'port': node_info.get('port'),
                    'name': node_info.get('name'),
                    'is_active': node_info.get('is_active'),
                    'source': node_info.get('source')
                }, msg="节点发现成功")
            else:
                return ErrorResponse(msg=result.get('error', '节点发现失败'))
        except Exception as e:
            logger.error(f"节点发现异常: {e}")
            return ErrorResponse(msg=f"节点发现失败: {str(e)}")
    @action(detail=True, methods=['post'])
    def prepare_key_negotiation(self, request, pk=None):
        try:
            source_node_id = pk
            target_node_id = request.data.get('target_node_id')
            set_request_msg(request, f'密钥协商准备(节点{source_node_id}→{target_node_id})')
            if not target_node_id:
                return ErrorResponse(msg="缺少目标节点ID")
            logger.info(f"准备密钥协商: {source_node_id} -> {target_node_id}")
            negotiation_service = KeyNegotiationService(source_node_id)
            result = negotiation_service.prepare_key_negotiation(target_node_id)
            if result.get('success'):
                return SuccessResponse(data={
                    'source_node_id': result.get('source_node_id'),
                    'target_node_id': result.get('target_node_id'),
                    'target_kyber_public_key': result.get('target_kyber_public_key'),
                    'target_falcon_public_key': result.get('target_falcon_public_key'),
                    'target_ip_address': result.get('target_ip_address'),
                    'target_port': result.get('target_port'),
                    'target_name': result.get('target_name'),
                    'keys_source': result.get('keys_source'),
                    'discovery_source': result.get('discovery_source')
                }, msg="密钥协商准备完成")
            else:
                return ErrorResponse(msg=result.get('error', '密钥协商准备失败'))
        except Exception as e:
            logger.error(f"密钥协商准备异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"密钥协商准备失败: {str(e)}")
    def destroy(self, request, *args, **kwargs):
        from django.db import transaction as db_transaction
        try:
            instance = self.get_object()
            node_id = instance.node_id
            node_name = instance.name
            set_request_msg(request, f'删除节点({node_name}, ID:{node_id})')
            logger.info(f" 开始删除节点: {node_name} (ID: {node_id})")
            from .models import SessionKey, Transaction, Message, FalconKeyPair, KeyDistributionLog
            session_count = SessionKey.objects.filter(
                models.Q(node1=instance) | models.Q(node2=instance)
            ).count()
            transaction_count = Transaction.objects.filter(
                models.Q(from_node=instance) | models.Q(to_node=instance)
            ).count()
            message_count = Message.objects.filter(
                models.Q(sender=instance) | models.Q(receiver=instance)
            ).count()
            falcon_key_count = FalconKeyPair.objects.filter(node=instance).count()
            key_log_count = KeyDistributionLog.objects.filter(node=instance).count()
            total_related = session_count + transaction_count + message_count + falcon_key_count + key_log_count
            logger.info(f" 关联数据统计:")
            logger.info(f"   - 会话密钥记录: {session_count}")
            logger.info(f"   - 交易记录: {transaction_count}")
            logger.info(f"   - 消息记录: {message_count}")
            logger.info(f"   - Falcon密钥对: {falcon_key_count}")
            logger.info(f"   - 密钥分发日志: {key_log_count}")
            logger.info(f"   - 总计: {total_related} 条关联记录")
            backup_deleted = self._delete_node_backup_files(node_id)
            with db_transaction.atomic():
                logger.info(f" 开始数据库事务删除...")
                if session_count > 0:
                    deleted_sessions = SessionKey.objects.filter(
                        models.Q(node1=instance) | models.Q(node2=instance)
                    ).delete()
                    logger.info(f"    删除会话密钥: {deleted_sessions[0]} 条")
                if transaction_count > 0:
                    deleted_transactions = Transaction.objects.filter(
                        models.Q(from_node=instance) | models.Q(to_node=instance)
                    ).delete()
                    logger.info(f"    删除交易记录: {deleted_transactions[0]} 条")
                if message_count > 0:
                    deleted_messages = Message.objects.filter(
                        models.Q(sender=instance) | models.Q(receiver=instance)
                    ).delete()
                    logger.info(f"    删除消息记录: {deleted_messages[0]} 条")
                if falcon_key_count > 0:
                    deleted_falcon = FalconKeyPair.objects.filter(node=instance).delete()
                    logger.info(f"    删除Falcon密钥对: {deleted_falcon[0]} 条")
                if key_log_count > 0:
                    deleted_logs = KeyDistributionLog.objects.filter(node=instance).delete()
                    logger.info(f"    删除密钥分发日志: {deleted_logs[0]} 条")
                instance.delete()
                logger.info(f"    删除节点记录: {node_name}")
            logger.info(f" 节点 {node_name} (ID: {node_id}) 及其所有关联数据删除成功")
            return SuccessResponse(
                data={
                    'deleted_node': {
                        'node_id': node_id,
                        'name': node_name
                    },
                    'deleted_related_data': {
                        'session_keys': session_count,
                        'transactions': transaction_count,
                        'messages': message_count,
                        'falcon_keys': falcon_key_count,
                        'key_logs': key_log_count,
                        'total': total_related
                    },
                    'backup_files_deleted': backup_deleted
                },
                msg=f"节点 {node_name} 及其所有关联数据删除成功"
            )
        except Exception as e:
            logger.error(f" 删除节点失败: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return ErrorResponse(msg=f"删除节点失败: {str(e)}")
    def _delete_node_backup_files(self, node_id):
        try:
            import os
            backup_dir = os.path.join(os.path.dirname(__file__), 'falcon_keys_backup')
            backup_file = os.path.join(backup_dir, f'node_{node_id}_falcon_keys.json')
            if os.path.exists(backup_file):
                os.remove(backup_file)
                logger.info(f"    删除备份文件: {backup_file}")
                return True
            else:
                logger.info(f"   ℹ 备份文件不存在: {backup_file}")
                return False
        except Exception as e:
            logger.warning(f"    删除备份文件失败: {e}")
            return False
    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        from django.db import transaction as db_transaction
        try:
            node_ids = request.data.get('node_ids', [])
            if not node_ids:
                return ErrorResponse(msg="请提供要删除的节点ID列表")
            if not isinstance(node_ids, list):
                return ErrorResponse(msg="node_ids必须是数组格式")
            set_request_msg(request, f'批量删除节点({",".join(str(i) for i in node_ids)})')
            logger.info(f" 开始批量删除节点: {node_ids}")
            nodes_to_delete = Node.objects.filter(node_id__in=node_ids)
            found_node_ids = list(nodes_to_delete.values_list('node_id', flat=True))
            missing_node_ids = [nid for nid in node_ids if nid not in found_node_ids]
            if missing_node_ids:
                logger.warning(f"以下节点不存在: {missing_node_ids}")
            if not nodes_to_delete.exists():
                return ErrorResponse(msg="没有找到要删除的节点")
            total_stats = {
                'session_keys': 0,
                'transactions': 0,
                'messages': 0,
                'falcon_keys': 0,
                'key_logs': 0
            }
            deleted_nodes = []
            backup_files_deleted = 0
            with db_transaction.atomic():
                for node in nodes_to_delete:
                    logger.info(f" 统计节点 {node.node_id} 的关联数据")
                    from .models import SessionKey, Transaction, Message, FalconKeyPair, KeyDistributionLog
                    session_count = SessionKey.objects.filter(
                        models.Q(node1=node) | models.Q(node2=node)
                    ).count()
                    transaction_count = Transaction.objects.filter(
                        models.Q(from_node=node) | models.Q(to_node=node)
                    ).count()
                    message_count = Message.objects.filter(
                        models.Q(sender=node) | models.Q(receiver=node)
                    ).count()
                    falcon_key_count = FalconKeyPair.objects.filter(node=node).count()
                    key_log_count = KeyDistributionLog.objects.filter(node=node).count()
                    total_stats['session_keys'] += session_count
                    total_stats['transactions'] += transaction_count
                    total_stats['messages'] += message_count
                    total_stats['falcon_keys'] += falcon_key_count
                    total_stats['key_logs'] += key_log_count
                    if self._delete_node_backup_files(node.node_id):
                        backup_files_deleted += 1
                    deleted_nodes.append({
                        'node_id': node.node_id,
                        'name': node.name,
                        'related_data': {
                            'session_keys': session_count,
                            'transactions': transaction_count,
                            'messages': message_count,
                            'falcon_keys': falcon_key_count,
                            'key_logs': key_log_count,
                            'total': session_count + transaction_count + message_count + falcon_key_count + key_log_count
                        }
                    })
                    node.delete()
                    logger.info(f" 节点 {node.node_id} 删除成功")
            total_stats['total'] = sum(total_stats.values())
            logger.info(f" 批量删除完成: {len(deleted_nodes)} 个节点")
            logger.info(f" 总关联数据: {total_stats['total']} 条")
            return SuccessResponse(
                data={
                    'deleted_nodes': deleted_nodes,
                    'total_deleted_nodes': len(deleted_nodes),
                    'missing_nodes': missing_node_ids,
                    'total_deleted_related_data': total_stats,
                    'backup_files_deleted': backup_files_deleted
                },
                msg=f"成功删除 {len(deleted_nodes)} 个节点及其所有关联数据"
            )
        except Exception as e:
            logger.error(f" 批量删除节点失败: {str(e)}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return ErrorResponse(msg=f"批量删除节点失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def cleanup_blockchain_data(self, request):
        try:
            from django.db import transaction
            from .models import SessionKey, Message, Transaction
            session_count = SessionKey.objects.count()
            message_count = Message.objects.count()
            transaction_count = Transaction.objects.count()
            with transaction.atomic():
                SessionKey.objects.all().delete()
                Message.objects.all().delete()
                Transaction.objects.all().delete()
                reset_nodes = request.data.get('reset_nodes', False)
                reset_count = 0
                if reset_nodes:
                    for node in Node.objects.all():
                        if node.status in ['kyber_uploaded', 'partial_key_received', 'falcon_generated', 'active']:
                            node.status = 'registered'
                            node.save(update_fields=['status'])
                            reset_count += 1
            logger.info(f"区块链数据清理完成: 会话{session_count}个, 消息{message_count}个, 交易{transaction_count}个")
            return SuccessResponse(
                data={
                    'cleaned_sessions': session_count,
                    'cleaned_messages': message_count,
                    'cleaned_transactions': transaction_count,
                    'reset_nodes': reset_count
                },
                msg=f"清理完成：会话{session_count}个，消息{message_count}个，交易{transaction_count}个"
            )
        except Exception as e:
            logger.error(f"清理区块链数据失败: {e}")
            return ErrorResponse(msg=f"清理失败: {str(e)}")
class BlockViewSet(CustomModelViewSet):
    queryset = Block.objects.all()
    serializer_class = BlockSerializer
    ordering = ['-block_number']
class TransactionViewSet(CustomModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    ordering = ['-timestamp']
    @action(detail=False, methods=['get'])
    def by_type(self, request):
        try:
            tx_types = Transaction.objects.values('tx_type').annotate(count=Count('id'))
            return SuccessResponse(data=list(tx_types), msg="获取交易类型统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取交易统计失败: {str(e)}")
class SessionKeyViewSet(CustomModelViewSet):
    queryset = SessionKey.objects.all()
    serializer_class = SessionKeySerializer
    extra_filter_class = []
    ordering = ['-id']
    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'initiate', 'initiate_kyber_agreement', 'verify_and_decrypt', 'send_message', 'decrypt_message', 'destroy', 'update', 'partial_update', 'check_expiration', 'cleanup_expired', 'expiration_stats']:
            return []
        return super().get_permissions()
    def get_serializer_class(self):
        if self.action == 'create':
            return SessionKeyCreateSerializer
        return SessionKeySerializer
    def get_queryset(self):
        try:
            # 自动将已过期但状态未更新的会话标记为 expired
            now = timezone.now()
            expired_count = SessionKey.objects.filter(
                expires_at__lt=now,
                status__in=['initiated', 'established', 'blockchain_recorded']
            ).update(status='expired')
            if expired_count:
                logger.info(f"【会话列表】自动标记 {expired_count} 个过期会话")

            result = SessionKey.objects.all().order_by('-id')
            result = self._apply_search_filters(result)
            return result
        except Exception as e:
            logger.error(f"【会话列表】获取会话查询集失败: {e}")
            import traceback
            traceback.print_exc()
            return SessionKey.objects.all().order_by('-id')
    def _apply_search_filters(self, queryset):
        try:
            initiator_node = self.request.query_params.get('initiator_node', '').strip()
            target_node = self.request.query_params.get('target_node', '').strip()
            status = self.request.query_params.get('status', '').strip()
            logger.info(f"【会话搜索】应用过滤条件 - initiator_node: {initiator_node}, target_node: {target_node}, status: {status}")
            if initiator_node:
                queryset = queryset.filter(node1__node_id__icontains=initiator_node)
                logger.info(f"【会话搜索】按发起节点过滤后: {queryset.count()} 个会话")
            if target_node:
                queryset = queryset.filter(node2__node_id__icontains=target_node)
                logger.info(f"【会话搜索】按目标节点过滤后: {queryset.count()} 个会话")
            if status:
                queryset = queryset.filter(status=status)
                logger.info(f"【会话搜索】按状态过滤后: {queryset.count()} 个会话")
            return queryset
        except Exception as e:
            logger.error(f"【会话搜索】应用过滤条件失败: {e}")
            return queryset
    def _sync_nodes_with_current_blockchain(self, blockchain_config):
        try:
            blockchain_service = BlockchainService()
            result = blockchain_service.get_all_nodes_from_blockchain()
            if result.get('success'):
                nodes = result.get('nodes', [])
                for node_info in nodes:
                    node_id = node_info.get('node_id')
                    if node_id:
                        Node.objects.filter(node_id=node_id).update(
                            blockchain_config=blockchain_config
                        )
                        logger.info(f"节点 {node_id} 已关联到区块链配置 {blockchain_config.name}")
        except Exception as e:
            logger.error(f"同步节点到区块链配置失败: {e}")
    @action(detail=False, methods=['post'])
    def initiate(self, request):
        try:
            node1_id = request.data.get('node1_id') or request.data.get('initiator_node') or request.data.get('from_node_id')
            node2_id = request.data.get('node2_id') or request.data.get('target_node') or request.data.get('to_node_id')
            set_request_msg(request, f'发起会话密钥协商(节点{node1_id}↔{node2_id})')
            session_type = request.data.get('session_type', 'aes_falcon')
            expires_at = request.data.get('expires_at')
            if not node1_id or not node2_id:
                return ErrorResponse(msg="缺少必要的节点ID参数")
            from .models import Node
            import base64
            try:
                node1 = Node.objects.get(node_id=node1_id)
                node2 = Node.objects.get(node_id=node2_id)
                if not all([node1.kyber_public_key, node1.kyber_private_key]):
                    return ErrorResponse(msg=f"节点 {node1_id} Kyber密钥不完整")
                if not all([node2.kyber_public_key, node2.kyber_private_key]):
                    return ErrorResponse(msg=f"节点 {node2_id} Kyber密钥不完整")
                if session_type == 'aes_falcon':
                    # Falcon 密钥检查：如果缺失则自动生成
                    for node_obj, nid in [(node1, node1_id), (node2, node2_id)]:
                        if not all([node_obj.falcon_public_key, node_obj.falcon_private_key]):
                            logger.info(f"[initiate] 节点 {nid} Falcon密钥缺失，自动生成...")
                            auto_svc = NodeService(nid)
                            auto_result = auto_svc.generate_falcon_keypair()
                            if not auto_result.get('success'):
                                return ErrorResponse(
                                    msg=f"节点 {nid} Falcon密钥不完整，自动生成失败: {auto_result.get('message')}。"
                                        f"请在节点管理中手动为该节点生成Falcon密钥。"
                                )
                            # 刷新节点对象
                            node_obj.refresh_from_db()
                            logger.info(f"[initiate] 节点 {nid} Falcon密钥自动生成成功")
                    # 再次验证
                    if not all([node1.falcon_public_key, node1.falcon_private_key]):
                        return ErrorResponse(msg=f"节点 {node1_id} Falcon密钥不完整，请在节点管理中生成Falcon密钥")
                    if not all([node2.falcon_public_key, node2.falcon_private_key]):
                        return ErrorResponse(msg=f"节点 {node2_id} Falcon密钥不完整，请在节点管理中生成Falcon密钥")
                node1_kyber_len = len(base64.b64decode(node1.kyber_public_key))
                node2_kyber_len = len(base64.b64decode(node2.kyber_public_key))
                level_map = {800: "Kyber-512", 1184: "Kyber-768", 1568: "Kyber-1024"}
                node1_level = level_map.get(node1_kyber_len, f"Unknown({node1_kyber_len})")
                node2_level = level_map.get(node2_kyber_len, f"Unknown({node2_kyber_len})")
                if node1_kyber_len != node2_kyber_len:
                    logger.info(f" 跨安全级别{session_type}会话: {node1_id}({node1_level}) -> {node2_id}({node2_level})")
                else:
                    logger.info(f" 同安全级别{session_type}会话: {node1_id}({node1_level}) -> {node2_id}({node2_level})")
            except Node.DoesNotExist as e:
                return ErrorResponse(msg=f"节点不存在: {str(e)}")
            node1_service = NodeService(node1_id)
            use_predist = request.data.get('use_predistributed', False)

            if use_predist:
                # 从发送方（node1）的本地密钥池文件中取用一条密钥
                # 密钥池是单向的：node1→node2 的池只在 node1 本地
                from .key_pool_local_storage import consume_key_from_local

                local_key = consume_key_from_local(node1_id, node2_id)
                if not local_key:
                    return ErrorResponse(
                        msg=f"发送方节点 {node1_id} 的本地密钥池中没有可用的 {node1_id}→{node2_id} 预分配密钥。"
                            f"请先通过「线上预分配」为 {node1_id}→{node2_id} 方向生成并下发密钥池。"
                    )

                import json as _json, hashlib, time as _time
                session_hash = hashlib.sha256(
                    f"{node1_id}_{node2_id}_{_time.time()}".encode()
                ).hexdigest()[:16]
                session_id = f"predist_{session_hash}"
                from datetime import timedelta
                exp = timezone.now() + timedelta(hours=24)
                if expires_at:
                    try:
                        from django.utils.dateparse import parse_datetime
                        exp = parse_datetime(expires_at) or exp
                    except:
                        pass

                # 会话密钥直接存储明文 hex（节点已解密），不再存加密密文
                session_obj = SessionKey.objects.create(
                    session_id=session_id,
                    node1=node1, node2=node2,
                    encrypted_session_key=local_key['key_hex'],
                    key_exchange_data=_json.dumps({
                        'source': 'predistributed_local',
                        'pool_id': local_key['pool_id'],
                        'key_index': local_key['key_index'],
                        'algorithm': local_key['algorithm'],
                        'key_hash': local_key['key_hash'],
                    }),
                    session_type=session_type,
                    status='established',
                    expires_at=exp,
                )

                # 更新数据库中的预分配记录状态
                from .models import PreDistributedKey
                PreDistributedKey.objects.filter(
                    pool_id=local_key['pool_id'],
                    key_index=local_key['key_index'],
                ).update(status='used', used_at=timezone.now(), used_by_session=session_obj)

                return SuccessResponse(data={
                    'success': True,
                    'session_id': session_id,
                    'session_pk': session_obj.pk,
                    'source': 'predistributed_local',
                    'algorithm': local_key['algorithm'],
                    'pool_id': local_key['pool_id'],
                    'key_index': local_key['key_index'],
                }, msg="使用本地预分配密钥建立会话成功")

            if session_type == 'kyber_kem':
                result = node1_service.initiate_kyber_key_agreement(node2_id, expires_at=expires_at)
                success_msg = "Kyber密钥协商完成"
            else:
                result = node1_service.initiate_session_key_exchange(node2_id, expires_at=expires_at)
                success_msg = "AES+Falcon会话密钥交换发起成功"
            if result['success']:
                return SuccessResponse(data=result, msg=success_msg)
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            return ErrorResponse(msg=f"会话建立失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def initiate_kyber_agreement(self, request):
        try:
            node1_id = request.data.get('node1_id') or request.data.get('initiator_node')
            node2_id = request.data.get('node2_id') or request.data.get('target_node')
            if not node1_id or not node2_id:
                return ErrorResponse(msg="缺少必要的节点ID参数")
            node1_service = NodeService(node1_id)
            result = node1_service.initiate_kyber_key_agreement(node2_id)
            if result['success']:
                return SuccessResponse(data=result, msg="Kyber密钥分发完成")
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            return ErrorResponse(msg=f"Kyber密钥分发失败: {str(e)}")
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        try:
            session: SessionKey = SessionKey.objects.get(pk=pk)
            set_request_msg(request, f'发送加密消息(会话{pk})')
            if hasattr(request, 'data') and request.data:
                data = request.data
            elif hasattr(request, 'POST') and request.POST:
                data = request.POST
            else:
                import json
                try:
                    data = json.loads(request.body.decode('utf-8'))
                except:
                    return ErrorResponse(msg="无法解析请求数据")
            sender_node_id = data.get('sender_node_id')
            content = data.get('content')
            if not sender_node_id or content is None:
                return ErrorResponse(msg="缺少必要的参数: sender_node_id 或 content")

            # 使用新的会话失效检查服务
            from .session_invalidation_service import SessionInvalidationService
            validity_check = SessionInvalidationService.check_session_validity(session)
            if not validity_check['valid']:
                return ErrorResponse(msg=validity_check['message'])

            # 验证会话是否可用于发送消息
            send_check = SessionInvalidationService.validate_session_for_message_sending(session)
            if not send_check['can_send']:
                return ErrorResponse(msg=send_check['message'])
            if not session.key_exchange_data or not session.encrypted_session_key:
                return ErrorResponse(msg="会话密钥数据不完整")
            if session.node1.node_id == sender_node_id:
                sender = session.node1
                receiver = session.node2
            elif session.node2.node_id == sender_node_id:
                sender = session.node2
                receiver = session.node1
            else:
                return ErrorResponse(msg="发送方不属于该会话")
            import base64, json as _json
            try:
                pkg = _json.loads(session.key_exchange_data)
            except Exception as e:
                logger.error(f"解析key_exchange_data失败: {e}")
                return ErrorResponse(msg="会话数据格式错误")

            try:
                if pkg.get('source') == 'predistributed_local':
                    # 本地预分配密钥会话：session key 直接存储为 hex
                    session_key = bytes.fromhex(session.encrypted_session_key)
                    logger.info(f"[PreDistLocal] 从本地预分配密钥恢复会话密钥, 长度: {len(session_key)} bytes")
                    node_service = NodeService(sender.node_id)

                elif pkg.get('source') == 'predistributed':
                    # 预分配密钥会话：从加密数据中恢复 AES 密钥
                    logger.info(f"[PreDist] 使用预分配密钥恢复会话密钥, 算法: {pkg.get('algorithm')}")
                    enc_data = _json.loads(session.encrypted_session_key)
                    predist_alg = pkg.get('algorithm', 'kyber_kem')

                    if predist_alg == 'kyber_kem':
                        # 预分配 Kyber KEM: 使用 DLL decaps 恢复 shared_secret，再 AES-GCM 解密
                        decaps_node = session.node2
                        if not decaps_node.kyber_private_key:
                            return ErrorResponse(msg=f"节点 {decaps_node.node_id} 没有Kyber私钥")

                        kem_ct = base64.b64decode(enc_data['kem_ciphertext'])
                        encrypted_aes_key = base64.b64decode(enc_data['encrypted_aes_key'])
                        kem_nonce = base64.b64decode(enc_data['nonce'])
                        kem_tag = base64.b64decode(enc_data['tag'])
                        enc_variant = enc_data.get('variant', 512)

                        receiver_sk = base64.b64decode(decaps_node.kyber_private_key)

                        # 根据私钥实际长度确定 Kyber 变体，避免公私钥变体不一致导致解封装失败
                        sk_len_map = {1632: 512, 2400: 768, 3168: 1024}
                        sk_variant = sk_len_map.get(len(receiver_sk))
                        if sk_variant is not None and sk_variant != enc_variant:
                            logger.error(
                                f"[PreDist/Kyber] 变体不一致: 预分配使用variant={enc_variant}(基于公钥), "
                                f"但节点私钥长度={len(receiver_sk)}字节(variant={sk_variant}). "
                                f"节点 {decaps_node.node_id} 的公私钥来自不同Kyber变体，需要重新生成密钥。"
                            )
                            return ErrorResponse(
                                msg=f"Kyber密钥不一致: 预分配时使用Kyber-{enc_variant}公钥加密，"
                                    f"但节点私钥为Kyber-{sk_variant}({len(receiver_sk)}字节)。"
                                    f"请在节点管理中重新生成 {decaps_node.node_id} 的密钥，然后重新预分配。"
                            )

                        from .real_crypto_with_fallback import RealKyberKEM
                        kyber = RealKyberKEM(enc_variant)
                        shared_secret = kyber.decaps(kem_ct, receiver_sk)

                        from Crypto.Cipher import AES as AES_Cipher
                        aes_kem_key = shared_secret[:32]
                        cipher = AES_Cipher.new(aes_kem_key, AES_Cipher.MODE_GCM, nonce=kem_nonce)
                        session_key = cipher.decrypt_and_verify(encrypted_aes_key, kem_tag)
                        logger.info(f"[PreDist/Kyber] DLL decaps + AES-GCM 恢复会话密钥成功, 长度: {len(session_key)} bytes")
                    else:
                        # Falcon 格密码: 用私钥解密
                        target_node = session.node2
                        if not target_node.falcon_private_key:
                            return ErrorResponse(msg=f"节点 {target_node.node_id} 没有Falcon私钥")
                        from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
                        falcon_dec = FalconAESSessionKeyEncryption(
                            security_level=enc_data.get('security_level', 512)
                        )
                        dec_result = falcon_dec.decrypt_aes_key_with_falcon(
                            ciphertext_b64=enc_data['ciphertext'],
                            private_key_b64=target_node.falcon_private_key
                        )
                        if not dec_result['success']:
                            return ErrorResponse(msg=f"Falcon解密失败: {dec_result.get('message')}")
                        session_key = dec_result['session_key']
                        logger.info(f"[PreDist/Falcon] 恢复会话密钥成功, 长度: {len(session_key)} bytes")

                    node_service = NodeService(sender.node_id)

                elif session.session_type == 'kyber_kem':
                    # Kyber KEM会话：通过DLL decaps恢复shared_secret，再解密AES会话密钥
                    logger.info(f"[KyberKEM] 处理Kyber KEM会话，使用DLL decaps恢复会话密钥")

                    # 确定哪个节点的私钥用于decaps
                    # 会话密钥是用target节点(node2)的公钥encaps的
                    # 所以需要用node2的私钥decaps
                    decaps_node = session.node2
                    if not decaps_node.kyber_partial_key_data:
                        return ErrorResponse(msg=f"节点 {decaps_node.node_id} 没有Kyber无证书密钥数据")

                    session_key = NodeService.recover_kyber_kem_session_key(
                        session.encrypted_session_key,
                        decaps_node.kyber_partial_key_data
                    )
                    logger.info(
                        f"[KyberCL] 通过无证书格密码Dec恢复会话密钥成功, "
                        f"长度: {len(session_key)} bytes"
                    )
                    node_service = NodeService(receiver.node_id)
                else:
                    # Falcon会话：使用Falcon格密码解密AES会话密钥
                    logger.info(f"[Falcon] 使用Falcon格密码解密AES会话密钥")
                    encrypted_by = pkg.get('encrypted_by', '')
                    if encrypted_by == 'falcon_lattice_encryption':
                        # 新格式：使用 Falcon 格密码加密的会话密钥
                        from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
                        falcon_security = pkg.get('security_level', 512)
                        falcon_dec = FalconAESSessionKeyEncryption(security_level=falcon_security)
                        # 使用接收方（target）的私钥解密
                        target_node = session.node2
                        if not target_node.falcon_private_key:
                            return ErrorResponse(msg=f"节点 {target_node.node_id} 没有Falcon私钥")
                        dec_result = falcon_dec.decrypt_aes_key_with_falcon(
                            ciphertext_b64=session.encrypted_session_key,
                            private_key_b64=target_node.falcon_private_key
                        )
                        if not dec_result['success']:
                            return ErrorResponse(msg=f"Falcon解密AES密钥失败: {dec_result.get('message')}")
                        session_key = dec_result['session_key']
                        logger.info(f"✓ Falcon格密码解密AES密钥成功，长度: {len(session_key)} bytes")
                    else:
                        # 兼容旧格式：从key_exchange_data中直接获取session_key
                        session_key_b64 = pkg.get('session_key')
                        if not session_key_b64:
                            return ErrorResponse(msg="会话密钥数据不完整")
                        session_key = base64.b64decode(session_key_b64)
                        logger.info(f"✓ 旧格式Falcon会话密钥解码成功，长度: {len(session_key)} bytes")
                    node_service = NodeService(sender.node_id)
                    logger.info(f"✓ 使用发送方节点 {sender.node_id} 的NodeService")
            except Exception as e:
                logger.error(f"❌ 提取会话密钥失败: {e}")
                import traceback
                traceback.print_exc()
                return ErrorResponse(msg=f"会话密钥提取失败: {str(e)}")

            try:
                plaintext = content.encode('utf-8')
                logger.info(f"准备加密消息，明文长度: {len(plaintext)} bytes")
                logger.info(f"会话密钥长度: {len(session_key)} bytes")

                try:
                    ciphertext, nonce = node_service.real_aes.encrypt(plaintext, session_key)
                    logger.info(f"✓ 消息加密成功，密文长度: {len(ciphertext)}, nonce长度: {len(nonce)}")
                except Exception as encrypt_err:
                    logger.error(f"❌ 消息加密失败: {encrypt_err}")
                    import traceback
                    traceback.print_exc()
                    return ErrorResponse(msg=f"消息加密失败: {str(encrypt_err)}")
            except Exception as e:
                logger.error(f"❌ 消息加密异常: {e}")
                import traceback
                traceback.print_exc()
                return ErrorResponse(msg=f"消息加密异常: {str(e)}")

            payload = {
                'ciphertext': base64.b64encode(ciphertext).decode('utf-8'),
                'nonce': base64.b64encode(nonce).decode('utf-8'),
                'alg': 'AES-256-GCM'
            }
            import hashlib
            import time
            timestamp = str(int(time.time() * 1000))
            msg_hash_input = f"{sender.node_id}_{receiver.node_id}_{timestamp}"
            msg_hash = hashlib.sha256(msg_hash_input.encode()).hexdigest()[:32]
            message_id = f"msg_{msg_hash}"

            logger.info(f"准备保存消息，message_id: {message_id}")
            logger.info(f"payload结构: ciphertext长度={len(payload['ciphertext'])}, nonce长度={len(payload['nonce'])}")

            message = Message.objects.create(
                message_id=message_id,
                session=session,
                sender=sender,
                receiver=receiver,
                encrypted_content=_json.dumps(payload, ensure_ascii=False),
                message_type='text',
                delivered=True,
                read=False,
            )
            logger.info(f"✓ 消息已保存，message_id: {message_id}, db_id: {message.id}")

            # 消息上链：将消息记录（密文哈希、发送方、接收方等）上传到区块链
            try:
                import hashlib as _hashlib
                ciphertext_hash = _hashlib.sha256(
                    payload['ciphertext'].encode('utf-8')
                ).hexdigest()
                from .blockchain_service import BlockchainService
                blockchain_svc = BlockchainService()
                if blockchain_svc.is_connected():
                    chain_result = blockchain_svc.record_message(
                        message_id=str(message.id),
                        session_id=str(session.session_id),
                        sender_node_id=str(sender.node_id),
                        receiver_node_id=str(receiver.node_id),
                        ciphertext_hash=ciphertext_hash,
                        algorithm=payload.get('alg', 'AES-256-GCM')
                    )
                    if chain_result.get('success'):
                        logger.info(
                            f"✓ 消息 {message.id} 已上链, "
                            f"tx_hash={chain_result.get('tx_hash', 'N/A')}"
                        )
                    else:
                        logger.warning(
                            f"消息 {message.id} 上链失败: "
                            f"{chain_result.get('error', 'unknown')}"
                        )
                else:
                    logger.info(f"区块链未连接，跳过消息 {message.id} 上链")
            except Exception as chain_err:
                logger.warning(f"消息上链异常（不影响消息发送）: {chain_err}")

            # 确保所有返回数据都是可序列化的
            timestamp_str = message.timestamp.isoformat() if message.timestamp else None
            response_data = {
                'message_id': int(message.id),  # 确保是整数
                'session_id': str(session.session_id),  # 确保是字符串
                'encrypted_content': {
                    'ciphertext': str(payload['ciphertext']),
                    'nonce': str(payload['nonce']),
                    'alg': str(payload['alg'])
                },
                'timestamp': timestamp_str
            }
            logger.info(f"✓ 返回响应数据: message_id={response_data['message_id']}, session_id={response_data['session_id']}")
            return SuccessResponse(data=response_data, msg="消息已加密并保存")
        except SessionKey.DoesNotExist:
            logger.error(f"❌ 会话不存在，pk={pk}")
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ 发送消息异常: {error_msg}")
            import traceback
            logger.error(f"❌ 异常堆栈:\n{traceback.format_exc()}")
            traceback.print_exc()
            if "base64" in error_msg.lower():
                return ErrorResponse(msg="会话密钥编码错误")
            elif "json" in error_msg.lower():
                return ErrorResponse(msg="会话数据格式错误")
            elif "encrypt" in error_msg.lower():
                return ErrorResponse(msg="消息加密失败")
            else:
                return ErrorResponse(msg=f"发送消息失败: {error_msg}")
    @action(detail=True, methods=['post'])
    def decrypt_message(self, request, pk=None):
        try:
            session: SessionKey = SessionKey.objects.get(pk=pk)
            set_request_msg(request, f'解密消息(会话{pk})')
            if hasattr(request, 'data') and request.data:
                data = request.data
            elif hasattr(request, 'POST') and request.POST:
                data = request.POST
            else:
                import json
                try:
                    data = json.loads(request.body.decode('utf-8'))
                except:
                    return ErrorResponse(msg="无法解析请求数据")
            message_id = data.get('message_id')
            receiver_node_id = data.get('receiver_node_id')
            if not message_id or not receiver_node_id:
                return ErrorResponse(msg="缺少必要的参数: message_id 或 receiver_node_id")
            expiration_check = SessionKeyExpirationService.check_session_expiration(session)
            if expiration_check['expired']:
                SessionKeyExpirationService.mark_session_as_expired(session)
                reason = "会话密钥已过期"
                if 'expires_at' in expiration_check:
                    reason += f"（过期时间: {expiration_check['expires_at']}）"
                return ErrorResponse(msg=reason)
            try:
                message = Message.objects.get(pk=message_id, session=session)
            except Message.DoesNotExist:
                return ErrorResponse(msg="消息不存在")
            if message.receiver.node_id != receiver_node_id:
                return ErrorResponse(msg="解密方不是该消息的接收者")
            import base64, json as _json
            pkg = _json.loads(session.key_exchange_data)
            if pkg.get('source') == 'predistributed_local':
                # 本地预分配密钥会话：session key 直接存储为 hex
                session_key = bytes.fromhex(session.encrypted_session_key)
                logger.info(f"[PreDistLocal] 从本地预分配密钥恢复会话密钥, 长度: {len(session_key)} bytes")
                node_service = NodeService(receiver_node_id)
            elif pkg.get('source') == 'predistributed':
                # 预分配密钥会话
                enc_data = _json.loads(session.encrypted_session_key)
                predist_alg = pkg.get('algorithm', 'kyber_kem')
                if predist_alg == 'kyber_kem':
                    decaps_node = session.node2
                    if not decaps_node.kyber_private_key:
                        return ErrorResponse(msg=f"节点 {decaps_node.node_id} 没有Kyber私钥")
                    kem_ct = base64.b64decode(enc_data['kem_ciphertext'])
                    encrypted_aes_key = base64.b64decode(enc_data['encrypted_aes_key'])
                    kem_nonce = base64.b64decode(enc_data['nonce'])
                    kem_tag = base64.b64decode(enc_data['tag'])
                    variant = enc_data.get('variant', 512)
                    receiver_sk = base64.b64decode(decaps_node.kyber_private_key)
                    from .real_crypto_with_fallback import RealKyberKEM
                    kyber = RealKyberKEM(variant)
                    shared_secret = kyber.decaps(kem_ct, receiver_sk)
                    from Crypto.Cipher import AES as AES_Cipher
                    aes_kem_key = shared_secret[:32]
                    cipher = AES_Cipher.new(aes_kem_key, AES_Cipher.MODE_GCM, nonce=kem_nonce)
                    session_key = cipher.decrypt_and_verify(encrypted_aes_key, kem_tag)
                    logger.info(f"[PreDist/Kyber] DLL decaps 恢复会话密钥成功, 长度: {len(session_key)} bytes")
                else:
                    target_node = session.node2
                    if not target_node.falcon_private_key:
                        return ErrorResponse(msg=f"节点 {target_node.node_id} 没有Falcon私钥")
                    from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
                    falcon_dec = FalconAESSessionKeyEncryption(
                        security_level=enc_data.get('security_level', 512)
                    )
                    dec_result = falcon_dec.decrypt_aes_key_with_falcon(
                        ciphertext_b64=enc_data['ciphertext'],
                        private_key_b64=target_node.falcon_private_key
                    )
                    if not dec_result['success']:
                        return ErrorResponse(msg=f"Falcon解密失败: {dec_result.get('message')}")
                    session_key = dec_result['session_key']
                    logger.info(f"[PreDist/Falcon] 恢复会话密钥成功, 长度: {len(session_key)} bytes")
                node_service = NodeService(receiver_node_id)
            elif session.session_type == 'kyber_kem':
                # Kyber 无证书格密码会话：使用 Dec 算法恢复会话密钥
                logger.info(f"[KyberCL] 使用无证书格密码Dec恢复会话密钥进行消息解密")
                decaps_node = session.node2
                if not decaps_node.kyber_partial_key_data:
                    return ErrorResponse(msg=f"节点 {decaps_node.node_id} 没有Kyber无证书密钥数据")
                session_key = NodeService.recover_kyber_kem_session_key(
                    session.encrypted_session_key,
                    decaps_node.kyber_partial_key_data
                )
                node_service = NodeService(receiver_node_id)
                logger.info(
                    f"[KyberCL] 通过无证书格密码Dec恢复会话密钥成功, "
                    f"长度: {len(session_key)} bytes"
                )
            else:
                # Falcon会话：使用Falcon格密码解密AES会话密钥
                encrypted_by = pkg.get('encrypted_by', '')
                if encrypted_by == 'falcon_lattice_encryption':
                    from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
                    falcon_security = pkg.get('security_level', 512)
                    falcon_dec = FalconAESSessionKeyEncryption(security_level=falcon_security)
                    target_node = session.node2
                    if not target_node.falcon_private_key:
                        return ErrorResponse(msg=f"节点 {target_node.node_id} 没有Falcon私钥")
                    dec_result = falcon_dec.decrypt_aes_key_with_falcon(
                        ciphertext_b64=session.encrypted_session_key,
                        private_key_b64=target_node.falcon_private_key
                    )
                    if not dec_result['success']:
                        return ErrorResponse(msg=f"Falcon解密AES密钥失败: {dec_result.get('message')}")
                    session_key = dec_result['session_key']
                    logger.info(f"[Falcon] 格密码解密AES密钥成功，长度: {len(session_key)} bytes")
                else:
                    # 兼容旧格式
                    session_key_b64 = pkg.get('session_key')
                    if not session_key_b64:
                        return ErrorResponse(msg="会话密钥数据不完整")
                    session_key = base64.b64decode(session_key_b64)
                    logger.info(f"旧格式Falcon会话密钥解密，长度: {len(session_key)} bytes")
                node_service = NodeService(receiver_node_id)
            payload = _json.loads(message.encrypted_content)
            ciphertext = base64.b64decode(payload['ciphertext'])
            # 支持新旧格式：优先使用'nonce'，如果不存在则使用'nonce_tag'
            nonce_key = 'nonce' if 'nonce' in payload else 'nonce_tag'
            if nonce_key not in payload:
                return ErrorResponse(msg="消息数据格式错误：缺少nonce字段")
            nonce = base64.b64decode(payload[nonce_key])
            logger.info(f"解密消息，密文长度: {len(ciphertext)}, nonce长度: {len(nonce)}")
            plaintext = node_service.real_aes.decrypt(ciphertext, session_key, nonce)
            if not message.read:
                message.read = True
                message.save(update_fields=['read'])
            logger.info(f"消息解密成功，明文长度: {len(plaintext)}")
            return SuccessResponse(data={
                'message_id': message.id,
                'plaintext': plaintext.decode('utf-8', errors='replace')
            }, msg="消息解密成功")
        except SessionKey.DoesNotExist:
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            error_msg = str(e)
            if "base64" in error_msg.lower():
                return ErrorResponse(msg="消息编码错误")
            elif "json" in error_msg.lower():
                return ErrorResponse(msg="消息数据格式错误")
            elif "decrypt" in error_msg.lower():
                return ErrorResponse(msg="消息解密失败（密钥或数据可能已损坏）")
            elif "authentication" in error_msg.lower():
                return ErrorResponse(msg="消息认证失败（消息可能已被篡改）")
            else:
                return ErrorResponse(msg=f"解密消息失败: {error_msg}")
    @action(detail=True, methods=['get'])
    def get_messages(self, request, pk=None):
        try:
            session: SessionKey = SessionKey.objects.get(pk=pk)
            messages = Message.objects.filter(session=session).order_by('timestamp')
            message_list = []
            for msg in messages:
                try:
                    import base64, json as _json
                    pkg = _json.loads(session.key_exchange_data)
                    if session.session_type == 'kyber_kem':
                        session_key = base64.b64decode(session.encrypted_session_key)
                        node_service = NodeService(msg.receiver.node_id)
                    else:
                        encrypted_by = pkg.get('encrypted_by', '')
                        if encrypted_by == 'falcon_lattice_encryption':
                            from .falcon_aes_session_encryption import FalconAESSessionKeyEncryption
                            falcon_security = pkg.get('security_level', 512)
                            falcon_dec = FalconAESSessionKeyEncryption(security_level=falcon_security)
                            target_node = session.node2
                            dec_result = falcon_dec.decrypt_aes_key_with_falcon(
                                ciphertext_b64=session.encrypted_session_key,
                                private_key_b64=target_node.falcon_private_key
                            )
                            if not dec_result['success']:
                                raise ValueError(f"Falcon解密失败: {dec_result.get('message')}")
                            session_key = dec_result['session_key']
                        else:
                            session_key_b64 = pkg.get('session_key')
                            session_key = base64.b64decode(session_key_b64)
                        node_service = NodeService(msg.sender.node_id)
                    payload = _json.loads(msg.encrypted_content)
                    ciphertext = base64.b64decode(payload['ciphertext'])
                    # 支持新旧格式：优先使用'nonce'，如果不存在则使用'nonce_tag'
                    nonce_key = 'nonce' if 'nonce' in payload else 'nonce_tag'
                    if nonce_key not in payload:
                        raise ValueError("消息数据格式错误：缺少nonce字段")
                    nonce = base64.b64decode(payload[nonce_key])
                    plaintext = node_service.real_aes.decrypt(ciphertext, session_key, nonce)
                    message_list.append({
                        'id': msg.id,
                        'sender': msg.sender.node_id,
                        'receiver': msg.receiver.node_id,
                        'content': plaintext.decode('utf-8', errors='replace'),
                        'timestamp': msg.timestamp.isoformat(),
                        'read': msg.read
                    })
                except Exception as decrypt_error:
                    logger.warning(f"解密消息 {msg.id} 失败: {str(decrypt_error)}")
                    message_list.append({
                        'id': msg.id,
                        'sender': msg.sender.node_id,
                        'receiver': msg.receiver.node_id,
                        'content': '[加密消息]',
                        'timestamp': msg.timestamp.isoformat(),
                        'read': msg.read,
                        'encrypted': True
                    })
            return SuccessResponse(data={
                'messages': message_list,
                'total': len(message_list),
                'session_id': session.session_id
            }, msg="获取消息列表成功")
        except SessionKey.DoesNotExist:
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            logger.error(f"获取消息列表失败: {str(e)}")
            return ErrorResponse(msg=f"获取消息列表失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def verify_and_decrypt(self, request):
        try:
            session_id = request.data.get('session_id')
            receiver_node_id = request.data.get('receiver_node_id')
            set_request_msg(request, f'验证并解密会话密钥(会话{session_id})')
            key_package = request.data.get('key_package')
            if not session_id or not receiver_node_id or not key_package:
                missing_params = []
                if not session_id:
                    missing_params.append('session_id')
                if not receiver_node_id:
                    missing_params.append('receiver_node_id')
                if not key_package:
                    missing_params.append('key_package')
                return ErrorResponse(msg=f"缺少必要的参数: {', '.join(missing_params)}")
            receiver_service = NodeService(receiver_node_id)
            result = receiver_service.verify_and_decrypt_session_key(session_id, key_package)
            if result['success']:
                return SuccessResponse(data=result, msg="会话密钥验证和解密成功")
            else:
                error_msg = result.get('message', '未知错误')
                return ErrorResponse(msg=error_msg)
        except SessionKey.DoesNotExist:
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            error_msg = str(e)
            if "expired" in error_msg.lower():
                return ErrorResponse(msg="会话密钥已过期")
            elif "verification" in error_msg.lower():
                return ErrorResponse(msg="会话密钥验证失败")
            elif "signature" in error_msg.lower():
                return ErrorResponse(msg="签名验证失败")
            elif "base64" in error_msg.lower():
                return ErrorResponse(msg="数据编码格式错误")
            elif "json" in error_msg.lower():
                return ErrorResponse(msg="数据格式错误")
            else:
                return ErrorResponse(msg=f"会话密钥验证和解密失败: {error_msg}")
    def destroy(self, request, *args, **kwargs):
        try:
            session = self.get_object()
            session_id = session.session_id
            set_request_msg(request, f'删除会话({session_id})')
            message_count = session.messages.count()
            logger.info(f"准备删除会话 {session_id}，包含 {message_count} 条消息")
            invalidation_count = 0
            try:
                from .models import SessionKeyInvalidation
                invalidations = SessionKeyInvalidation.objects.filter(session=session)
                invalidation_count = invalidations.count()
                invalidations.delete()
                logger.info(f"已删除会话 {session_id} 的 {invalidation_count} 条失效记录")
            except Exception as inv_error:
                logger.warning(f"删除SessionKeyInvalidation记录时出错: {inv_error}")
            try:
                from .models import Message
                Message.objects.filter(session=session).delete()
                logger.info(f"已删除会话 {session_id} 的 {message_count} 条消息记录")
            except Exception as msg_error:
                logger.warning(f"删除Message记录时出错: {msg_error}")
            session.delete()
            logger.info(f"成功删除会话 {session_id}")
            return SuccessResponse(msg=f"会话删除成功，已清理 {invalidation_count} 条失效记录和 {message_count} 条相关消息")
        except Exception as e:
            logger.error(f"删除会话失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"删除会话失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def check_expiration(self, request):
        try:
            session_id = request.query_params.get('session_id')
            if session_id:
                session = SessionKey.objects.get(session_id=session_id)
                # 使用新的会话失效检查服务
                from .session_invalidation_service import SessionInvalidationService
                validity_check = SessionInvalidationService.check_session_validity(session)
                return SuccessResponse(data=validity_check, msg="会话状态检查完成")
            else:
                active_sessions = SessionKey.objects.filter(
                    status__in=['initiated', 'established', 'blockchain_recorded']
                )
                expired_sessions = []
                valid_sessions = []
                for session in active_sessions:
                    from .session_invalidation_service import SessionInvalidationService
                    validity_check = SessionInvalidationService.check_session_validity(session)
                    if not validity_check['valid']:
                        expired_sessions.append({
                            'session_id': session.session_id,
                            'expires_at': session.expires_at,
                            'status': session.status,
                            'reason': validity_check.get('reason')
                        })
                    else:
                        valid_sessions.append({
                            'session_id': session.session_id,
                            'expires_at': session.expires_at,
                            'time_remaining_seconds': validity_check.get('time_remaining_seconds'),
                            'status': session.status
                        })
                return SuccessResponse(data={
                    'total_sessions': len(active_sessions),
                    'valid_sessions': len(valid_sessions),
                    'expired_sessions': len(expired_sessions),
                    'expired_list': expired_sessions,
                    'valid_list': valid_sessions
                }, msg="会话过期检查完成")
        except SessionKey.DoesNotExist:
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            logger.error(f"检查会话过期状态失败: {str(e)}")
            return ErrorResponse(msg=f"检查失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def cleanup_expired(self, request):
        try:
            from .session_invalidation_service import SessionInvalidationService
            result = SessionInvalidationService.cleanup_expired_sessions()
            if result['success']:
                return SuccessResponse(data={
                    'cleaned_count': result['cleaned_count'],
                    'message': result['message']
                }, msg="过期会话清理完成")
            else:
                return ErrorResponse(msg=result.get('message', '清理失败'))
        except Exception as e:
            logger.error(f"清理过期会话失败: {str(e)}")
            return ErrorResponse(msg=f"清理失败: {str(e)}")

    @action(detail=True, methods=['get'])
    def invalidation_history(self, request, pk=None):
        """获取会话的失效历史记录"""
        try:
            session = self.get_object()
            from .session_invalidation_service import SessionInvalidationService
            history = SessionInvalidationService.get_session_invalidation_history(session)
            return SuccessResponse(data={
                'session_id': session.session_id,
                'current_status': session.status,
                'invalidation_count': len(history),
                'history': history
            }, msg="会话失效历史获取成功")
        except SessionKey.DoesNotExist:
            return ErrorResponse(msg="会话不存在")
        except Exception as e:
            logger.error(f"获取会话失效历史失败: {str(e)}")
            return ErrorResponse(msg=f"获取失败: {str(e)}")

    @action(detail=False, methods=['get'])
    def node_invalidated_sessions(self, request):
        """获取由某个节点密钥更新导致失效的所有会话"""
        try:
            node_id = request.query_params.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")

            node = Node.objects.get(node_id=node_id)
            from .session_invalidation_service import SessionInvalidationService
            result = SessionInvalidationService.get_node_invalidated_sessions(node)
            return SuccessResponse(data=result, msg="节点失效会话列表获取成功")
        except Node.DoesNotExist:
            return ErrorResponse(msg="节点不存在")
        except Exception as e:
            logger.error(f"获取节点失效会话失败: {str(e)}")
            return ErrorResponse(msg=f"获取失败: {str(e)}")

    @action(detail=False, methods=['get'])
    def session_status_summary(self, request):
        """获取会话状态统计摘要"""
        try:
            node_id = request.query_params.get('node_id')
            node = None
            if node_id:
                node = Node.objects.get(node_id=node_id)

            from .session_invalidation_service import SessionInvalidationService
            result = SessionInvalidationService.get_session_status_summary(node)
            return SuccessResponse(data=result, msg="会话状态统计获取成功")
        except Node.DoesNotExist:
            return ErrorResponse(msg="节点不存在")
        except Exception as e:
            logger.error(f"获取会话状态统计失败: {str(e)}")
            return ErrorResponse(msg=f"获取失败: {str(e)}")

    @action(detail=False, methods=['get'])
    def expiration_stats(self, request):
        try:
            current_time = timezone.now()
            total_sessions = SessionKey.objects.count()
            expired_sessions = SessionKey.objects.filter(expires_at__lt=current_time).count()
            active_sessions = SessionKey.objects.filter(
                status__in=['initiated', 'established', 'blockchain_recorded'],
                expires_at__gt=current_time
            ).count()
            revoked_sessions = SessionKey.objects.filter(status='revoked').count()
            one_hour_later = current_time + timedelta(hours=1)
            expiring_soon = SessionKey.objects.filter(
                expires_at__lte=one_hour_later,
                expires_at__gt=current_time,
                status__in=['initiated', 'established', 'blockchain_recorded']
            ).count()
            return SuccessResponse(data={
                'total_sessions': total_sessions,
                'expired_sessions': expired_sessions,
                'active_sessions': active_sessions,
                'revoked_sessions': revoked_sessions,
                'expiring_soon': expiring_soon,
                'current_time': current_time.isoformat()
            }, msg="会话过期统计获取成功")
        except Exception as e:
            logger.error(f"获取会话过期统计失败: {str(e)}")
            return ErrorResponse(msg=f"获取统计失败: {str(e)}")
class MessageViewSet(CustomModelViewSet):
    queryset = Message.objects.all()
    serializer_class = MessageSerializer
    def get_serializer_class(self):
        if self.action == 'create':
            return MessageCreateSerializer
        return MessageSerializer
class BlockchainConfigViewSet(CustomModelViewSet):
    queryset = BlockchainConfig.objects.all()
    serializer_class = BlockchainConfigSerializer
    def get_serializer_class(self):
        if self.action == 'create':
            return BlockchainConfigCreateSerializer
        return BlockchainConfigSerializer

    def get_permissions(self):
        if self.action in ['list', 'create', 'status', 'deploy_contract', 'nodes_from_blockchain', 'active', 'sync_database_to_blockchain']:
            return []
        return super().get_permissions()
    @action(detail=False, methods=['post'])
    def deploy_contract(self, request):
        set_request_msg(request, '部署智能合约')
        if not BlockchainConfig.objects.filter(is_active=True).exists():
            return ErrorResponse(msg="请先在区块链配置页面添加并激活一个区块链配置（Ganache provider URL + 私钥）")
        try:
            blockchain_service = BlockchainService()
            result = blockchain_service.compile_and_deploy_contract()
            if result['success']:
                return SuccessResponse(data=result, msg="智能合约部署成功")
            else:
                return ErrorResponse(msg=f"智能合约部署失败: {result['error']}")
        except Exception as e:
            return ErrorResponse(msg=f"智能合约部署失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def status(self, request):
        try:
            blockchain_service = BlockchainService()
            result = blockchain_service.get_blockchain_status()
            if result['success']:
                status_data = {k: v for k, v in result.items() if k != 'success'}
                return SuccessResponse(data=status_data, msg="获取区块链状态成功")
            else:
                return ErrorResponse(msg=f"获取区块链状态失败: {result['error']}")
        except Exception as e:
            return ErrorResponse(msg=f"获取区块链状态失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def nodes_from_blockchain(self, request):
        try:
            logger.info("【获取区块链节点】开始处理请求")
            blockchain_service = BlockchainService()
            logger.info("【获取区块链节点】BlockchainService初始化成功")
            result = blockchain_service.get_all_nodes_from_blockchain()
            logger.info(f"【获取区块链节点】get_all_nodes_from_blockchain返回: success={result.get('success')}, nodes_count={len(result.get('nodes', []))}")
            if result['success']:
                import base64
                def _to_b64(v):
                    if v is None:
                        return ''
                    try:
                        if isinstance(v, (bytes, bytearray)):
                            return base64.b64encode(v).decode('utf-8')
                        if hasattr(v, 'hex'):
                            hex_str = v.hex()
                            return base64.b64encode(bytes.fromhex(hex_str)).decode('utf-8')
                        if isinstance(v, str):
                            if v.startswith('0x'):
                                hex_data = v[2:]
                                if len(hex_data) % 2 != 0:
                                    hex_data = '0' + hex_data
                                return base64.b64encode(bytes.fromhex(hex_data)).decode('utf-8')
                            else:
                                try:
                                    return base64.b64encode(v.encode('utf-8')).decode('utf-8')
                                except UnicodeEncodeError:
                                    return base64.b64encode(v.encode('latin-1')).decode('utf-8')
                        if hasattr(v, '__str__'):
                            str_v = str(v)
                            return base64.b64encode(str_v.encode('utf-8')).decode('utf-8')
                    except Exception as e:
                        logger.warning(f"转换公钥数据为base64失败: {e}, 数据类型: {type(v)}, 数据: {repr(v)}")
                        return ''
                    return ''
                processed_nodes = []
                active_blockchain_config = (
                    BlockchainConfig.objects.filter(is_active=True)
                    .order_by('-update_datetime', '-create_datetime', '-id')
                    .first()
                )
                for node in result['nodes']:
                    processed_node = node.copy()
                    if 'kyber_public_key' in processed_node:
                        processed_node['kyber_public_key'] = _to_b64(processed_node['kyber_public_key'])
                    if 'falcon_public_key' in processed_node:
                        processed_node['falcon_public_key'] = _to_b64(processed_node['falcon_public_key'])
                    if active_blockchain_config:
                        processed_node['blockchain_config'] = active_blockchain_config.id
                        logger.info(f"节点 {processed_node.get('node_id', 'unknown')} 标记为配置: {active_blockchain_config.id}")
                    processed_nodes.append(processed_node)
                logger.info(f"【获取区块链节点】返回 {len(processed_nodes)} 个节点，均属于当前活跃配置")
                if len(processed_nodes) == 0:
                    logger.warning("【获取区块链节点】区块链节点为空，尝试从数据库同步节点")
                    try:
                        from pqkds.models import Node
                        db_nodes = Node.objects.all()
                        if db_nodes.exists():
                            logger.info(f"【获取区块链节点】数据库中有 {db_nodes.count()} 个节点，开始同步到区块链")
                            sync_count = 0
                            for db_node in db_nodes:
                                try:
                                    logger.info(f"【获取区块链节点】同步节点 {db_node.node_id} 到区块链")
                                    blockchain_service.register_node_on_blockchain(
                                        db_node.node_id,
                                        db_node.name or db_node.node_id,
                                        str(db_node.ip_address) if db_node.ip_address else '127.0.0.1',
                                        db_node.port or 0
                                    )
                                    sync_count += 1
                                    logger.info(f"【获取区块链节点】节点 {db_node.node_id} 同步成功")
                                except Exception as sync_err:
                                    logger.warning(f"【获取区块链节点】节点 {db_node.node_id} 同步失败: {sync_err}")
                                    continue
                            logger.info(f"【获取区块链节点】成功同步 {sync_count} 个节点到区块链")
                            logger.info("【获取区块链节点】重新获取区块链节点")
                            result = blockchain_service.get_all_nodes_from_blockchain()
                            if result.get('success'):
                                processed_nodes = []
                                for node in result.get('nodes', []):
                                    processed_node = node.copy()
                                    if 'kyber_public_key' in processed_node:
                                        processed_node['kyber_public_key'] = _to_b64(processed_node['kyber_public_key'])
                                    if 'falcon_public_key' in processed_node:
                                        processed_node['falcon_public_key'] = _to_b64(processed_node['falcon_public_key'])
                                    if active_blockchain_config:
                                        processed_node['blockchain_config'] = active_blockchain_config.id
                                    processed_nodes.append(processed_node)
                                logger.info(f"【获取区块链节点】重新获取后返回 {len(processed_nodes)} 个节点")
                    except Exception as sync_err:
                        logger.warning(f"【获取区块链节点】从数据库同步节点失败: {sync_err}")
                return SuccessResponse(data=processed_nodes, msg="获取区块链节点信息成功")
            else:
                error_msg = result.get('error', '未知错误')
                logger.error(f"【获取区块链节点】blockchain_service返回失败: {error_msg}")
                return ErrorResponse(msg=f"获取区块链节点信息失败: {error_msg}")
        except Exception as e:
            logger.error(f"【获取区块链节点】异常: {str(e)}", exc_info=True)
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"获取区块链节点信息失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def active(self, request):
        try:
            active_config = (
                BlockchainConfig.objects.filter(is_active=True)
                .order_by('-update_datetime', '-create_datetime', '-id')
                .first()
            )
            if active_config:
                serializer = self.get_serializer(active_config)
                return SuccessResponse(data=serializer.data, msg="获取活跃区块链配置成功")
            else:
                return ErrorResponse(msg="没有找到活跃的区块链配置")
        except Exception as e:
            return ErrorResponse(msg=f"获取区块链配置失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def sync_database_to_blockchain(self, request):
        try:
            set_request_msg(request, '同步数据库到区块链')
            logger.info("=" * 80)
            logger.info(" 开始自动同步：数据库  区块链")
            logger.info("=" * 80)
            sync_service = DatabaseToBlockchainSyncService()
            result = sync_service.sync_all_nodes_to_blockchain()
            if result['success']:
                logger.info("=" * 80)
                logger.info(" 自动同步完成！")
                logger.info("=" * 80)
                return SuccessResponse(
                    data=result,
                    msg=f"同步成功: 成功{result.get('synced_count', 0)}个，失败{result.get('failed_count', 0)}个"
                )
            else:
                logger.error("=" * 80)
                logger.error(" 自动同步失败！")
                logger.error("=" * 80)
                return ErrorResponse(
                    msg=result.get('message', '同步失败'),
                    data=result
                )
        except Exception as e:
            logger.error(f" 自动同步出错: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"同步出错: {str(e)}")
class FalconKeyPairViewSet(CustomModelViewSet):
    queryset = FalconKeyPair.objects.all()
    serializer_class = FalconKeyPairSerializer
    def get_serializer_class(self):
        if self.action in ['retrieve', 'list']:
            return FalconKeyPairDetailSerializer
        return FalconKeyPairSerializer
class KeyDistributionLogViewSet(CustomModelViewSet):
    queryset = KeyDistributionLog.objects.all()
    serializer_class = KeyDistributionLogSerializer
    ordering = ['-timestamp']
    def get_permissions(self):
        if self.action in ['list', 'stats']:
            return []
        return super().get_permissions()
    def get_queryset(self):
        try:
            params = self.request.query_params.copy()
            if 'success' in params and params.get('success') == '':
                params._mutable = True
                params.pop('success')
                params._mutable = False
                self.request._request.GET = params
        except Exception:
            pass
        return super().get_queryset()
    @action(detail=False, methods=['get'])
    def stats(self, request):
        try:
            stats = KeyDistributionLog.objects.values('action').annotate(
                total=Count('id'),
                success=Count('id', filter=Q(success=True)),
                failed=Count('id', filter=Q(success=False))
            )
            return SuccessResponse(data=list(stats), msg="获取日志统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取日志统计失败: {str(e)}")
class SystemStatsViewSet(CustomModelViewSet):
    queryset = Node.objects.none()
    serializer_class = NodeSerializer

    def get_serializer_class(self):
        if getattr(self, 'swagger_fake_view', False):
            return NodeSerializer
        return NodeSerializer

    def get_permissions(self):
        if self.action in ['overview', 'blockchain']:
            return []
        return super().get_permissions()
    @action(detail=False, methods=['get'])
    def overview(self, request):
        try:
            data = {
                'total_nodes': Node.objects.count(),
                'active_nodes': Node.objects.filter(status='active').count(),
                'total_transactions': Transaction.objects.count(),
                'total_sessions': SessionKey.objects.count(),
                'total_messages': Message.objects.count(),
                'latest_block': Block.objects.aggregate(max_block=Max('block_number'))['max_block'] or 0,
            }
            return SuccessResponse(data=data, msg="获取系统统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取系统统计失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def blockchain(self, request):
        try:
            data = {
                'total_blocks': Block.objects.count(),
                'total_transactions': Transaction.objects.count(),
                'kyber_uploads': Transaction.objects.filter(tx_type='kyber_upload').count(),
                'falcon_uploads': Transaction.objects.filter(tx_type='falcon_upload').count(),
                'session_exchanges': Transaction.objects.filter(tx_type='session_key_exchange').count(),
            }
            latest_block = Block.objects.order_by('-block_number').first()
            if latest_block:
                data['latest_block_hash'] = latest_block.block_hash
                data['latest_block_time'] = latest_block.timestamp
            return SuccessResponse(data=data, msg="获取区块链统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取区块链统计失败: {str(e)}")
@api_view(['POST'])
@permission_classes([AllowAny])
def generate_falcon_keypair_with_scheme(request):
    try:
        node_id = request.data.get('node_id')
        scheme = request.data.get('scheme', 'v2')
        set_request_msg(request, f'生成Falcon密钥对(节点{node_id}, 方案:{scheme})')
        if not node_id:
            return ErrorResponse(msg="节点ID不能为空")
        if scheme == 'v1':
            return ErrorResponse(msg="V1方案已移除，请使用V2方案（基于陷门的密钥生成）")
        if scheme != 'v2':
            return ErrorResponse(msg="无效的方案选择，当前仅支持 v2")
        try:
            node = Node.objects.get(node_id=node_id)
        except Node.DoesNotExist:
            return ErrorResponse(msg=f"节点 {node_id} 不存在")
        from .node_service import NodeService
        node_service = NodeService(node_id)
        result = node_service.generate_falcon_keys_v2()
        scheme_name = "V2(基于陷门函数方案)"
        if result['success']:
            return SuccessResponse(
                data={
                    **result,
                    'scheme': scheme,
                    'scheme_name': scheme_name
                },
                msg=f"Falcon密钥生成成功 - {scheme_name}"
            )
        else:
            return ErrorResponse(msg=result['message'])
    except Exception as e:
        import traceback
        traceback.print_exc()
        return ErrorResponse(msg=f"Falcon密钥生成失败: {str(e)}")
@api_view(['POST'])
@permission_classes([AllowAny])
def save_falcon_keys(request):
    try:
        node_id = request.data.get('node_id')
        set_request_msg(request, f'保存Falcon密钥(节点{node_id})')
        falcon_private_key = request.data.get('falcon_private_key')
        falcon_public_key = request.data.get('falcon_public_key')
        if not all([node_id, falcon_private_key, falcon_public_key]):
            return ErrorResponse(msg="缺少必要参数")
        from django.db import connections
        for conn in connections.all():
            conn.close()
        import time
        time.sleep(0.1)
        with transaction.atomic():
            updated_count = Node.objects.filter(node_id=node_id).update(
                falcon_private_key=falcon_private_key,
                falcon_public_key=falcon_public_key,
                status='falcon_v2_generated'
            )
            if updated_count > 0:
                logger.info(f" 节点 {node_id} Falcon密钥保存成功")
                return SuccessResponse(msg="Falcon密钥保存成功")
            else:
                return ErrorResponse(msg="未找到指定节点")
    except Exception as e:
        logger.error(f"保存Falcon密钥失败: {e}")
        return ErrorResponse(msg=f"保存失败: {str(e)}")
@api_view(['GET'])
@permission_classes([AllowAny])
def get_and_verify_falcon_public_key(request, node_id):
    try:
        logger.info(f" 开始获取并验证节点 {node_id} 的Falcon公钥")
        verification_service = FalconKeyVerificationService()
        result = verification_service.get_and_verify_falcon_public_key(node_id)
        if result['success']:
            logger.info(f" 节点 {node_id} Falcon公钥验证成功")
            return SuccessResponse(
                data={
                    'node_id': node_id,
                    'falcon_public_key': result['falcon_public_key'],
                    'key_size_mb': result['key_size_mb'],
                    'verification_result': result['verification_result'],
                    'verified': True
                },
                msg="Falcon公钥获取并验证成功"
            )
        else:
            logger.error(f" 节点 {node_id} Falcon公钥验证失败: {result.get('error', 'Unknown error')}")
            return ErrorResponse(
                msg=f"公钥验证失败: {result.get('error', 'Unknown error')}",
                data={
                    'node_id': node_id,
                    'verified': False,
                    'error_step': result.get('step', 'unknown')
                }
            )
    except Exception as e:
        logger.error(f" 获取并验证节点 {node_id} Falcon公钥时发生异常: {e}")
        return ErrorResponse(msg=f"验证异常: {str(e)}")
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_falcon_public_key_integrity(request):
    try:
        node_id = request.data.get('node_id')
        falcon_public_key = request.data.get('falcon_public_key')
        if not node_id or not falcon_public_key:
            return ErrorResponse(msg="缺少必要参数: node_id 和 falcon_public_key")
        logger.info(f" 开始验证节点 {node_id} 的Falcon公钥完整性")
        verification_service = FalconKeyVerificationService()
        result = verification_service.verify_falcon_public_key_integrity(node_id, falcon_public_key)
        if result['success'] and result.get('verified', False):
            logger.info(f" 节点 {node_id} Falcon公钥完整性验证通过")
            return SuccessResponse(
                data={
                    'node_id': node_id,
                    'verified': True,
                    'calculated_hash': result['calculated_hash'],
                    'blockchain_hash': result['blockchain_hash'],
                    'verification_status': result['verification_status']
                },
                msg="Falcon公钥完整性验证通过"
            )
        else:
            logger.error(f" 节点 {node_id} Falcon公钥完整性验证失败")
            return ErrorResponse(
                msg=f"完整性验证失败: {result.get('error', 'Unknown error')}",
                data={
                    'node_id': node_id,
                    'verified': False,
                    'calculated_hash': result.get('calculated_hash', ''),
                    'blockchain_hash': result.get('blockchain_hash', ''),
                    'verification_status': result.get('verification_status', 'failed')
                }
            )
    except Exception as e:
        logger.error(f" 验证Falcon公钥完整性时发生异常: {e}")
        return ErrorResponse(msg=f"验证异常: {str(e)}")
@api_view(['POST'])
@permission_classes([AllowAny])
def batch_verify_falcon_public_keys(request):
    try:
        node_ids = request.data.get('node_ids', [])
        if not node_ids or not isinstance(node_ids, list):
            return ErrorResponse(msg="缺少必要参数: node_ids (数组)")
        logger.info(f" 开始批量验证 {len(node_ids)} 个节点的Falcon公钥")
        verification_service = FalconKeyVerificationService()
        result = verification_service.batch_verify_falcon_public_keys(node_ids)
        if result['success']:
            logger.info(f" 批量验证完成: {result['success_count']}/{result['total_nodes']} 成功")
            return SuccessResponse(
                data={
                    'total_nodes': result['total_nodes'],
                    'success_count': result['success_count'],
                    'failure_count': result['failure_count'],
                    'results': result['results'],
                    'summary': result['summary']
                },
                msg=f"批量验证完成: {result['summary']}"
            )
        else:
            logger.error(f" 批量验证失败: {result.get('error', 'Unknown error')}")
            return ErrorResponse(msg=f"批量验证失败: {result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.error(f" 批量验证Falcon公钥时发生异常: {e}")
        return ErrorResponse(msg=f"批量验证异常: {str(e)}")
    @action(detail=False, methods=['post'])
    def invalidate_sessions_on_kyber_update(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            logger.info(f"处理节点 {node_id} 的Kyber密钥更新导致的会话失效")
            node_service = NodeService(node_id)
            from .key_update_and_session_invalidation_service import KeyUpdateAndSessionInvalidationService
            invalidation_service = KeyUpdateAndSessionInvalidationService(node_id)
            result = invalidation_service.invalidate_sessions_on_kyber_key_update()
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"处理Kyber密钥更新失效异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"处理失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def invalidate_sessions_on_falcon_update(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            logger.info(f"处理节点 {node_id} 的Falcon密钥更新导致的会话失效")
            node_service = NodeService(node_id)
            from .key_update_and_session_invalidation_service import KeyUpdateAndSessionInvalidationService
            invalidation_service = KeyUpdateAndSessionInvalidationService(node_id)
            result = invalidation_service.invalidate_sessions_on_falcon_key_update()
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"处理Falcon密钥更新失效异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"处理失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def invalidate_sessions_on_both_keys_update(self, request):
        try:
            node_id = request.data.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            logger.info(f"处理节点 {node_id} 的双密钥更新导致的会话失效")
            node_service = NodeService(node_id)
            result = node_service.update_both_keys_and_invalidate_sessions()
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"处理双密钥更新失效异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"处理失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def manually_revoke_session(self, request):
        try:
            node_id = request.data.get('node_id')
            session_id = request.data.get('session_id')
            if not node_id or not session_id:
                return ErrorResponse(msg="缺少必要参数: node_id, session_id")
            logger.info(f"手动撤销会话: {session_id}")
            node_service = NodeService(node_id)
            result = node_service.manually_revoke_session(session_id)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"手动撤销会话异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"撤销失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def get_session_invalidation_history(self, request):
        try:
            node_id = request.query_params.get('node_id')
            session_id = request.query_params.get('session_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            logger.info(f"查询会话失效历史: node_id={node_id}, session_id={session_id}")
            node_service = NodeService(node_id)
            result = node_service.get_session_invalidation_history(
                session_id=session_id,
                node_id=node_id
            )
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"查询会话失效历史异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"查询失败: {str(e)}")
    @action(detail=False, methods=['get'])
    def get_node_key_version_info(self, request):
        try:
            node_id = request.query_params.get('node_id')
            if not node_id:
                return ErrorResponse(msg="缺少必要参数: node_id")
            logger.info(f"查询节点 {node_id} 的密钥版本信息")
            node_service = NodeService(node_id)
            result = node_service.get_node_key_version_info()
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result['message'])
        except Exception as e:
            logger.error(f"查询密钥版本信息异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"查询失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def generate_complete_kyber_keypair(self, request):
        try:
            node_id = request.data.get('node_id')
            kgc_partial_key_data = request.data.get('kgc_partial_key_data')
            if not node_id or not kgc_partial_key_data:
                return ErrorResponse(msg="缺少必要参数: node_id, kgc_partial_key_data")
            logger.info(f"节点{node_id}开始生成完整Kyber密钥对")
            node_service = NodeService(node_id)
            result = node_service.generate_complete_kyber_keypair_from_partial_key(kgc_partial_key_data)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"生成完整Kyber密钥对异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"生成失败: {str(e)}")
    @action(detail=False, methods=['post'])
    def generate_complete_falcon_keypair(self, request):
        try:
            node_id = request.data.get('node_id')
            kgc_partial_key_data = request.data.get('kgc_partial_key_data')
            if not node_id or not kgc_partial_key_data:
                return ErrorResponse(msg="缺少必要参数: node_id, kgc_partial_key_data")
            logger.info(f"节点{node_id}开始生成完整Falcon密钥对")
            node_service = NodeService(node_id)
            result = node_service.generate_complete_falcon_keypair_from_partial_key(kgc_partial_key_data)
            if result['success']:
                return SuccessResponse(data=result, msg=result['message'])
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"生成完整Falcon密钥对异常: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"生成失败: {str(e)}")



# ================================================================
#  密钥预分配 (Key Pool) ViewSet
# ================================================================
class KeyPoolViewSet(CustomModelViewSet):
    """基于格的安全密钥预分配管理"""
    from .models import PreDistributedKey
    queryset = PreDistributedKey.objects.all()
    from .serializers import PreDistributedKeySerializer
    serializer_class = PreDistributedKeySerializer
    extra_filter_class = []
    ordering = ['-id']

    def get_permissions(self):
        return []

    def get_queryset(self):
        from .models import PreDistributedKey
        now = timezone.now()

        # 自动删除过期且未使用的密钥
        expired_qs = PreDistributedKey.objects.filter(
            expires_at__lte=now,
            status__in=['unused', 'distributed', 'expired']
        )
        expired_count = expired_qs.count()
        if expired_count > 0:
            expired_qs.delete()
            logger.info(f"[KeyPool] 列表加载时自动删除 {expired_count} 条过期密钥")

        qs = PreDistributedKey.objects.all().order_by('-id')
        node1_id = self.request.query_params.get('node1_id', '').strip()
        node2_id = self.request.query_params.get('node2_id', '').strip()
        algorithm = self.request.query_params.get('algorithm', '').strip()
        status_filter = self.request.query_params.get('status', '').strip()
        pool_id = self.request.query_params.get('pool_id', '').strip()

        if node1_id and node2_id:
            qs = qs.filter(
                models.Q(node1__node_id=node1_id, node2__node_id=node2_id) |
                models.Q(node1__node_id=node2_id, node2__node_id=node1_id)
            )
        elif node1_id:
            qs = qs.filter(
                models.Q(node1__node_id=node1_id) | models.Q(node2__node_id=node1_id)
            )
        if algorithm:
            qs = qs.filter(algorithm=algorithm)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if pool_id:
            qs = qs.filter(pool_id=pool_id)
        return qs

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """批量预分配密钥"""
        try:
            node1_id = request.data.get('node1_id')
            node2_id = request.data.get('node2_id')
            algorithm = request.data.get('algorithm', 'kyber_kem')
            count = int(request.data.get('count', 50))
            expiry_hours = int(request.data.get('expiry_hours', 24))

            set_request_msg(request, f'预分配密钥({algorithm}, {node1_id}↔{node2_id}, {count}条)')

            if not node1_id or not node2_id:
                return ErrorResponse(msg="缺少 node1_id 或 node2_id")
            if count < 1 or count > 1000:
                return ErrorResponse(msg="count 范围: 1-1000")

            from .key_pool_service import KeyPoolService
            if algorithm == 'falcon_lattice':
                result = KeyPoolService.generate_falcon_pool(node1_id, node2_id, count, expiry_hours)
            else:
                result = KeyPoolService.generate_kyber_pool(node1_id, node2_id, count, expiry_hours)

            if result.get('success'):
                return SuccessResponse(data=result, msg=f"预分配完成: {result['generated']} 条")
            else:
                return ErrorResponse(msg=result.get('message', '预分配失败'))
        except Exception as e:
            logger.error(f"密钥预分配失败: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"预分配失败: {str(e)}")

    @action(detail=False, methods=['post'])
    def consume(self, request):
        """从密钥池取用一条密钥"""
        try:
            node1_id = request.data.get('node1_id')
            node2_id = request.data.get('node2_id')
            algorithm = request.data.get('algorithm')

            set_request_msg(request, f'取用预分配密钥({node1_id}↔{node2_id})')

            if not node1_id or not node2_id:
                return ErrorResponse(msg="缺少 node1_id 或 node2_id")

            from .key_pool_service import KeyPoolService
            result = KeyPoolService.consume_key(node1_id, node2_id, algorithm)

            if result.get('success'):
                return SuccessResponse(data=result, msg="密钥取用成功")
            else:
                return ErrorResponse(msg=result.get('message', '无可用密钥'))
        except Exception as e:
            return ErrorResponse(msg=f"密钥取用失败: {str(e)}")

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """密钥池统计"""
        try:
            node1_id = request.query_params.get('node1_id', '').strip()
            node2_id = request.query_params.get('node2_id', '').strip()

            from .key_pool_service import KeyPoolService
            result = KeyPoolService.get_pool_stats(
                node1_id=node1_id or None,
                node2_id=node2_id or None
            )
            return SuccessResponse(data=result, msg="获取统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取统计失败: {str(e)}")

    @action(detail=False, methods=['post'])
    def cleanup(self, request):
        """删除过期的未使用密钥（数据库 + 本地文件）"""
        try:
            set_request_msg(request, '清理过期预分配密钥')
            from .key_pool_service import KeyPoolService
            result = KeyPoolService.cleanup_expired()
            msg = f"已删除 {result['cleaned']} 条过期密钥"
            if result.get('local_cleaned'):
                msg += f"，清理 {result['local_cleaned']} 个本地过期文件"
            return SuccessResponse(data=result, msg=msg)
        except Exception as e:
            return ErrorResponse(msg=f"清理失败: {str(e)}")

    @action(detail=False, methods=['post'])
    def replenish(self, request):
        """检查并补充密钥池"""
        try:
            node1_id = request.data.get('node1_id')
            node2_id = request.data.get('node2_id')
            algorithm = request.data.get('algorithm', 'kyber_kem')
            target_size = int(request.data.get('target_size', 50))

            set_request_msg(request, f'补充密钥池({node1_id}↔{node2_id})')

            if not node1_id or not node2_id:
                return ErrorResponse(msg="缺少 node1_id 或 node2_id")

            from .key_pool_service import KeyPoolService
            result = KeyPoolService.check_and_replenish(node1_id, node2_id, algorithm, target_size)

            if result is None:
                return SuccessResponse(data={'replenished': False}, msg="密钥池余量充足，无需补充")
            if result.get('success'):
                return SuccessResponse(data=result, msg=f"补充完成: {result['generated']} 条")
            else:
                return ErrorResponse(msg=result.get('message', '补充失败'))
        except Exception as e:
            return ErrorResponse(msg=f"补充失败: {str(e)}")

    @action(detail=False, methods=['post'])
    def batch_delete(self, request):
        """
        批量删除预分配密钥。
        如果被删除的密钥已被某个会话使用，则将该会话状态改为 revoked（已撤销）。
        """
        try:
            ids = request.data.get('ids', [])
            if not ids:
                return ErrorResponse(msg="请选择要删除的密钥")

            set_request_msg(request, f'批量删除预分配密钥({len(ids)}条)')

            from .models import PreDistributedKey, SessionKey
            keys = PreDistributedKey.objects.filter(id__in=ids)
            total_count = keys.count()

            # 找出已被会话使用的密钥，撤销关联会话
            used_keys = keys.filter(status='used', used_by_session__isnull=False)
            revoked_session_ids = []
            for key in used_keys.select_related('used_by_session'):
                session = key.used_by_session
                if session and session.status not in ('revoked', 'expired'):
                    session.status = 'revoked'
                    session.save(update_fields=['status'])
                    revoked_session_ids.append(session.session_id)
                    logger.info(
                        f"[KeyPool] 密钥 {key.pool_id}#{key.key_index} 被删除，"
                        f"关联会话 {session.session_id} 已撤销"
                    )

            # 删除密钥
            deleted_count, _ = keys.delete()

            return SuccessResponse(data={
                'deleted': deleted_count,
                'revoked_sessions': len(revoked_session_ids),
                'revoked_session_ids': revoked_session_ids,
            }, msg=f"已删除 {deleted_count} 条密钥" + (
                f"，撤销 {len(revoked_session_ids)} 个关联会话" if revoked_session_ids else ""
            ))
        except Exception as e:
            logger.error(f"批量删除预分配密钥失败: {e}")
            return ErrorResponse(msg=f"删除失败: {str(e)}")

    # ================================================================
    #  线上预分配：生成 + 下发给发送方节点
    # ================================================================
    @action(detail=False, methods=['post'])
    def distribute(self, request):
        """
        生成单向密钥池（sender → receiver）。
        KDS 生成密钥后，仅用发送方的 Kyber 公钥加密，
        返回一份加密数据包，前端自动提交给 receive 接口完成下发。

        参数:
          sender_node_id: 发送方节点（密钥池持有者）
          receiver_node_id: 接收方节点（通信目标）
          count: 密钥数量
          expiry_hours: 有效期
        """
        try:
            sender_node_id = request.data.get('sender_node_id') or request.data.get('node1_id')
            receiver_node_id = request.data.get('receiver_node_id') or request.data.get('node2_id')
            count = int(request.data.get('count', 50))
            expiry_hours = int(request.data.get('expiry_hours', 24))

            set_request_msg(request, f'线上预分配密钥({sender_node_id}→{receiver_node_id}, {count}条)')

            if not sender_node_id or not receiver_node_id:
                return ErrorResponse(msg="缺少 sender_node_id 或 receiver_node_id")
            if count < 1 or count > 1000:
                return ErrorResponse(msg="count 范围: 1-1000")

            from .key_pool_service import KeyPoolService
            result = KeyPoolService.generate_distributable_pool(
                sender_node_id, receiver_node_id, count, expiry_hours
            )

            if result.get('success'):
                return SuccessResponse(data=result, msg=f"密钥池生成完成: {result['generated']} 条，等待发送方节点接收")
            else:
                return ErrorResponse(msg=result.get('message', '生成失败'))
        except Exception as e:
            logger.error(f"线上预分配失败: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"预分配失败: {str(e)}")

    @action(detail=False, methods=['post'])
    def receive(self, request):
        """
        节点接收加密的密钥池数据包，用自己的 Kyber 私钥解密，
        保存到本地文件。

        请求体:
        {
          "node_id": "node_alice",
          "encrypted_package": {
            "pool_id": "...",
            "peer_node_id": "node_bob",
            "algorithm": "kyber_kem",
            "variant": 512,
            "expires_at": "...",
            "encrypted_keys": [...]
          }
        }
        """
        try:
            node_id = request.data.get('node_id')
            package = request.data.get('encrypted_package')

            if not node_id or not package:
                return ErrorResponse(msg="缺少 node_id 或 encrypted_package")

            set_request_msg(request, f'节点 {node_id} 接收密钥池')

            # 获取节点的 Kyber 私钥
            from .models import Node
            try:
                node = Node.objects.get(node_id=node_id)
            except Node.DoesNotExist:
                return ErrorResponse(msg=f"节点 {node_id} 不存在")

            if not node.kyber_private_key:
                return ErrorResponse(msg=f"节点 {node_id} 没有 Kyber 私钥")

            import base64
            from .real_crypto_with_fallback import RealKyberKEM
            from Crypto.Cipher import AES as AES_Cipher

            variant = package.get('variant', 512)
            kyber = RealKyberKEM(variant)
            sk = base64.b64decode(node.kyber_private_key)

            pool_id = package.get('pool_id')
            peer_node_id = package.get('peer_node_id')
            algorithm = package.get('algorithm', 'kyber_kem')
            expires_at = package.get('expires_at', '')
            encrypted_keys = package.get('encrypted_keys', [])

            # 逐条解密
            decrypted_keys = []
            for ek in encrypted_keys:
                try:
                    kem_ct = base64.b64decode(ek['kem_ciphertext'])
                    enc_key = base64.b64decode(ek['encrypted_key'])
                    nonce = base64.b64decode(ek['nonce'])
                    tag = base64.b64decode(ek['tag'])

                    # Kyber decaps 恢复 shared_secret
                    shared_secret = kyber.decaps(kem_ct, sk)

                    # AES-GCM 解密恢复 AES 会话密钥
                    cipher = AES_Cipher.new(shared_secret[:32], AES_Cipher.MODE_GCM, nonce=nonce)
                    aes_key = cipher.decrypt_and_verify(enc_key, tag)

                    decrypted_keys.append({
                        'index': ek['index'],
                        'key_hex': aes_key.hex(),
                        'key_hash': ek['key_hash'],
                    })
                except Exception as e:
                    logger.warning(f"[Receive] 第 {ek.get('index')} 条解密失败: {e}")
                    continue

            if not decrypted_keys:
                return ErrorResponse(msg="所有密钥解密失败")

            # 保存到本地文件
            from .key_pool_local_storage import save_pool_to_local
            save_result = save_pool_to_local(
                node_id=node_id,
                peer_node_id=peer_node_id,
                pool_id=pool_id,
                algorithm=algorithm,
                keys=decrypted_keys,
                expires_at=expires_at,
            )

            logger.info(
                f"[Receive] 节点 {node_id} 接收密钥池 {pool_id}: "
                f"{len(decrypted_keys)}/{len(encrypted_keys)} 条解密成功"
            )

            return SuccessResponse(data={
                'pool_id': pool_id,
                'received': len(decrypted_keys),
                'total': len(encrypted_keys),
                'file_path': save_result.get('file_path'),
            }, msg=f"密钥池接收成功: {len(decrypted_keys)} 条密钥已保存到本地")

        except Exception as e:
            logger.error(f"接收密钥池失败: {e}")
            import traceback
            traceback.print_exc()
            return ErrorResponse(msg=f"接收失败: {str(e)}")

    @action(detail=False, methods=['get'])
    def local_stats(self, request):
        """获取节点本地密钥池统计"""
        try:
            node_id = request.query_params.get('node_id', '').strip()
            if not node_id:
                return ErrorResponse(msg="缺少 node_id")

            from .key_pool_local_storage import get_local_pool_stats
            result = get_local_pool_stats(node_id)
            return SuccessResponse(data=result, msg="获取本地密钥池统计成功")
        except Exception as e:
            return ErrorResponse(msg=f"获取统计失败: {str(e)}")