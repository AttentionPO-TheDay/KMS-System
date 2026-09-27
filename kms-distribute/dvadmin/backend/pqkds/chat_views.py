from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
import json
import base64
from datetime import datetime
from .chat_models import ChatMessage, ChatSession, ChatNotification
from .models import Node
from .node_service import NodeService
from .kgc_service import KGCService
import logging
logger = logging.getLogger(__name__)
@csrf_exempt
@require_http_methods(["POST"])
def send_message(request):
    try:
        data = json.loads(request.body)
        sender_id = data.get('sender_id')
        receiver_id = data.get('receiver_id')
        message_content = data.get('message')
        sender = Node.objects.get(node_id=sender_id)
        receiver = Node.objects.get(node_id=receiver_id)
        node_service = NodeService(sender_id)
        encrypted_message = node_service.encrypt_message(
            message_content,
            receiver.kyber_public_key
        )
        chat_msg = ChatMessage.objects.create(
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_content=message_content,
            encrypted_message=encrypted_message,
            timestamp=datetime.now()
        )
        return JsonResponse({
            'success': True,
            'message_id': chat_msg.id,
            'timestamp': chat_msg.timestamp.isoformat(),
            'encrypted': True
        })
    except Exception as e:
        logger.error(f"发送消息失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
@csrf_exempt
@require_http_methods(["GET"])
def get_messages(request):
    try:
        sender_id = request.GET.get('sender_id')
        receiver_id = request.GET.get('receiver_id')
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        all_messages = ChatMessage.objects.filter(
            (Q(sender_id=sender_id) & Q(receiver_id=receiver_id)) |
            (Q(sender_id=receiver_id) & Q(receiver_id=sender_id))
        ).order_by('timestamp')
        total_count = all_messages.count()
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        messages = all_messages[start_idx:end_idx]
        message_list = []
        for msg in messages:
            message_list.append({
                'id': msg.id,
                'sender_id': msg.sender_id,
                'receiver_id': msg.receiver_id,
                'message': msg.message_content,
                'timestamp': msg.timestamp.isoformat(),
                'encrypted': True
            })
        return JsonResponse({
            'success': True,
            'messages': message_list,
            'total': total_count,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        logger.error(f"获取消息失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
@csrf_exempt
@require_http_methods(["GET"])
def get_nodes(request):
    try:
        nodes = Node.objects.all().values('node_id', 'node_name', 'status')
        node_list = []
        for node in nodes:
            node_list.append({
                'node_id': node['node_id'],
                'node_name': node['node_name'],
                'status': node.get('status', 'active')
            })
        return JsonResponse({
            'success': True,
            'nodes': node_list
        })
    except Exception as e:
        logger.error(f"获取节点列表失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
def chat_page(request):
    try:
        return render(request, 'pqkds/chat.html', {
            'title': 'PQKDS加密聊天系统',
            'description': '后量子密码学端到端加密通信'
        })
    except Exception as e:
        logger.error(f"加载聊天页面失败: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': '加载聊天页面失败'
        }, status=500)