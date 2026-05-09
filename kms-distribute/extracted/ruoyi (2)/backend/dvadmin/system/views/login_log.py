from dvadmin.system.models import LoginLog
from dvadmin.utils.serializers import CustomModelSerializer
from dvadmin.utils.viewset import CustomModelViewSet
class LoginLogSerializer(CustomModelSerializer):
    class Meta:
        model = LoginLog
        fields = "__all__"
        read_only_fields = ["id"]
class LoginLogViewSet(CustomModelViewSet):
    queryset = LoginLog.objects.all()
    serializer_class = LoginLogSerializer
    extra_filter_class = []