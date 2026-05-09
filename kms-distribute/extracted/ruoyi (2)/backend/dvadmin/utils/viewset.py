from django.db import transaction
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.viewsets import ModelViewSet
from dvadmin.utils.filters import DataLevelPermissionsFilter
from dvadmin.utils.import_export_mixin import ExportSerializerMixin, ImportSerializerMixin
from dvadmin.utils.json_response import SuccessResponse, ErrorResponse, DetailResponse
from dvadmin.utils.permission import CustomPermission
from dvadmin.utils.models import get_custom_app_models
from dvadmin.system.models import FieldPermission, MenuField
from django_restql.mixins import QueryArgumentsMixin
class CustomModelViewSet(ModelViewSet, ImportSerializerMixin, ExportSerializerMixin, QueryArgumentsMixin):
    values_queryset = None
    ordering_fields = '__all__'
    create_serializer_class = None
    update_serializer_class = None
    filter_fields = '__all__'
    search_fields = ()
    extra_filter_class = [DataLevelPermissionsFilter]
    permission_classes = [CustomPermission]
    import_field_dict = {}
    export_field_label = {}
    def filter_queryset(self, queryset):
        for backend in set(set(self.filter_backends) | set(self.extra_filter_class or [])):
            queryset = backend().filter_queryset(self.request, queryset, self)
        return queryset
    def get_queryset(self):
        if getattr(self, 'values_queryset', None):
            return self.values_queryset
        return super().get_queryset()
    def get_serializer_class(self):
        action_serializer_name = f"{self.action}_serializer_class"
        action_serializer_class = getattr(self, action_serializer_name, None)
        if action_serializer_class:
            return action_serializer_class
        return super().get_serializer_class()
    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs.setdefault('context', self.get_serializer_context())
        can_see = self.get_menu_field(serializer_class)
        self.request.permission_fields = can_see
        if isinstance(self.request.data, list):
            with transaction.atomic():
                return serializer_class(many=True, *args, **kwargs)
        else:
            return serializer_class(*args, **kwargs)
    def get_menu_field(self, serializer_class):
        finded = False
        for model in get_custom_app_models():
            if model['object'] is serializer_class.Meta.model:
                finded = True
                break
        if finded is False:
            return []
        return MenuField.objects.filter(model=model['model']
        ).values('field_name', 'title')
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, request=request)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return DetailResponse(data=serializer.data, msg="新增成功")
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True, request=request)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True, request=request)
        return SuccessResponse(data=serializer.data, msg="获取成功")
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return DetailResponse(data=serializer.data, msg="获取成功")
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, request=request, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return DetailResponse(data=serializer.data, msg="更新成功")
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return DetailResponse(data=[], msg="删除成功")
    keys = openapi.Schema(description='主键列表', type=openapi.TYPE_ARRAY, items=openapi.TYPE_STRING)
    @swagger_auto_schema(request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['keys'],
        properties={'keys': keys}
    ), operation_summary='批量删除')
    @action(methods=['delete'], detail=False)
    def multiple_delete(self, request, *args, **kwargs):
        request_data = request.data
        keys = request_data.get('keys', None)
        if keys:
            self.get_queryset().filter(id__in=keys).delete()
            return SuccessResponse(data=[], msg="删除成功")
        else:
            return ErrorResponse(msg="未获取到keys字段")