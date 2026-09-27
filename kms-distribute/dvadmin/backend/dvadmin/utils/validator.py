from django.db import DataError
from rest_framework.exceptions import APIException
from rest_framework.validators import UniqueValidator
class CustomValidationError(APIException):
    def __init__(self, detail):
        self.detail = detail
def qs_exists(queryset):
    try:
        return queryset.exists()
    except (TypeError, ValueError, DataError):
        return False
def qs_filter(queryset, **kwargs):
    try:
        return queryset.filter(**kwargs)
    except (TypeError, ValueError, DataError):
        return queryset.none()
class CustomUniqueValidator(UniqueValidator):
    def filter_queryset(self, value, queryset, field_name):
        filter_kwargs = {'%s__%s' % (field_name, self.lookup): value}
        return qs_filter(queryset, **filter_kwargs)
    def exclude_current_instance(self, queryset, instance):
        if instance is not None:
            return queryset.exclude(pk=instance.pk)
        return queryset
    def __call__(self, value, serializer_field):
        field_name = serializer_field.source_attrs[-1]
        instance = getattr(serializer_field.parent, 'instance', None)
        queryset = self.queryset
        queryset = self.filter_queryset(value, queryset, field_name)
        queryset = self.exclude_current_instance(queryset, instance)
        if qs_exists(queryset):
            raise CustomValidationError(self.message)
    def __repr__(self):
        return super().__repr__()