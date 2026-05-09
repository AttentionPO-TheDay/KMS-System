from rest_framework import serializers
from rest_framework.fields import empty
from rest_framework.request import Request
from rest_framework.serializers import ModelSerializer
from django.utils.functional import cached_property
from rest_framework.utils.serializer_helpers import BindingDict
from dvadmin.system.models import Users
from django_restql.mixins import DynamicFieldsMixin
class CustomModelSerializer(DynamicFieldsMixin, ModelSerializer):
    modifier_field_id = "modifier"
    modifier_name = serializers.SerializerMethodField(read_only=True)
    def get_modifier_name(self, instance):
        if not hasattr(instance, "modifier"):
            return None
        queryset = (
            Users.objects.filter(id=instance.modifier)
            .values_list("name", flat=True)
            .first()
        )
        if queryset:
            return queryset
        return None
    creator_field_id = "creator"
    creator_name = serializers.SlugRelatedField(
        slug_field="name", source="creator", read_only=True
    )
    dept_belong_id_field_name = "dept_belong_id"
    create_datetime = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S", required=False, read_only=True
    )
    update_datetime = serializers.DateTimeField(
        format="%Y-%m-%d %H:%M:%S", required=False
    )
    def __init__(self, instance=None, data=empty, request=None, **kwargs):
        super().__init__(instance, data, **kwargs)
        self.request: Request = request or self.context.get("request", None)
    def save(self, **kwargs):
        return super().save(**kwargs)
    def create(self, validated_data):
        if self.request:
            if str(self.request.user) != "AnonymousUser":
                if self.modifier_field_id in self.fields.fields:
                    validated_data[self.modifier_field_id] = self.get_request_user_id()
                if self.creator_field_id in self.fields.fields:
                    validated_data[self.creator_field_id] = self.request.user
                if (
                    self.dept_belong_id_field_name in self.fields.fields
                    and validated_data.get(self.dept_belong_id_field_name, None) is None
                ):
                    validated_data[self.dept_belong_id_field_name] = getattr(
                        self.request.user, "dept_id", None
                    )
        return super().create(validated_data)
    def update(self, instance, validated_data):
        if self.request:
            if str(self.request.user) != "AnonymousUser":
                if self.modifier_field_id in self.fields.fields:
                    validated_data[self.modifier_field_id] = self.get_request_user_id()
            if hasattr(self.instance, self.modifier_field_id):
                setattr(
                    self.instance, self.modifier_field_id, self.get_request_user_id()
                )
        return super().update(instance, validated_data)
    def get_request_username(self):
        if getattr(self.request, "user", None):
            return getattr(self.request.user, "username", None)
        return None
    def get_request_name(self):
        if getattr(self.request, "user", None):
            return getattr(self.request.user, "name", None)
        return None
    def get_request_user_id(self):
        if getattr(self.request, "user", None):
            return getattr(self.request.user, "id", None)
        return None
    @property
    def errors(self):
        errors = super().errors
        verbose_errors = {}
        fields = {field.name: field.verbose_name for field in
                  self.Meta.model._meta.get_fields() if hasattr(field, 'verbose_name')}
        for field_name, error in errors.items():
            if field_name in fields:
                verbose_errors[str(fields[field_name])] = error
            else:
                verbose_errors[field_name] = error
        return verbose_errors