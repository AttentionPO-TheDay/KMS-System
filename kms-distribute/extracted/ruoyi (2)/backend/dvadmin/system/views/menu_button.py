from django.db.models import F
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from dvadmin.system.models import MenuButton, RoleMenuButtonPermission
from dvadmin.utils.json_response import DetailResponse, SuccessResponse
from dvadmin.utils.serializers import CustomModelSerializer
from dvadmin.utils.viewset import CustomModelViewSet
class MenuButtonSerializer(CustomModelSerializer):
    class Meta:
        model = MenuButton
        fields = ['id', 'name', 'value', 'api', 'method','menu']
        read_only_fields = ["id"]
class MenuButtonCreateUpdateSerializer(CustomModelSerializer):
    class Meta:
        model = MenuButton
        fields = "__all__"
        read_only_fields = ["id"]
class MenuButtonViewSet(CustomModelViewSet):
    queryset = MenuButton.objects.order_by('create_datetime')
    serializer_class = MenuButtonSerializer
    create_serializer_class = MenuButtonCreateUpdateSerializer
    update_serializer_class = MenuButtonCreateUpdateSerializer
    extra_filter_class = []
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True, request=request)
        return SuccessResponse(serializer.data,msg="获取成功")
    @action(methods=['get'],detail=False,permission_classes=[IsAuthenticated])
    def menu_button_all_permission(self,request):
        is_superuser = request.user.is_superuser
        if is_superuser:
            queryset = MenuButton.objects.values_list('value',flat=True)
        else:
            role_id = request.user.role.values_list('id', flat=True)
            queryset = RoleMenuButtonPermission.objects.filter(role__in=role_id).values_list('menu_button__value',flat=True).distinct()
        return DetailResponse(data=queryset)