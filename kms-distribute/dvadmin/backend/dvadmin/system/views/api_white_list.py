from dvadmin.system.models import ApiWhiteList
from dvadmin.utils.serializers import CustomModelSerializer
from dvadmin.utils.viewset import CustomModelViewSet
class ApiWhiteListSerializer(CustomModelSerializer):
    class Meta:
        model = ApiWhiteList
        fields = "__all__"
        read_only_fields = ["id"]
class ApiWhiteListViewSet(CustomModelViewSet):
    queryset = ApiWhiteList.objects.all()
    serializer_class = ApiWhiteListSerializer