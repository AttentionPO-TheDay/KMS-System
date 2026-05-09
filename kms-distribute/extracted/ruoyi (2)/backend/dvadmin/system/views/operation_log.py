from dvadmin.system.models import OperationLog
from dvadmin.utils.serializers import CustomModelSerializer
from dvadmin.utils.viewset import CustomModelViewSet

class OperationLogSerializer(CustomModelSerializer):
    class Meta:
        model = OperationLog
        fields = "__all__"
        read_only_fields = ["id"]

class OperationLogCreateUpdateSerializer(CustomModelSerializer):
    class Meta:
        model = OperationLog
        fields = '__all__'

class OperationLogViewSet(CustomModelViewSet):
    queryset = OperationLog.objects.order_by('-create_datetime')
    serializer_class = OperationLogSerializer
    extra_filter_class = []  # 禁用数据级权限过滤，允许查看所有操作日志
    filter_fields = ['request_modular', 'request_method', 'status']
    search_fields = ['request_path', 'request_msg', 'request_modular']

    def get_permissions(self):
        """允许所有用户查看操作日志"""
        if self.action in ['list', 'retrieve']:
            return []
        return super().get_permissions()
