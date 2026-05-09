from django.conf import settings
from django.db import connection
def is_tenants_mode():
    return hasattr(connection, "tenant") and connection.tenant.schema_name
def _get_all_dictionary():
    from dvadmin.system.models import Dictionary
    queryset = Dictionary.objects.filter(status=True, is_value=False)
    data = []
    for instance in queryset:
        data.append(
            {
                "id": instance.id,
                "value": instance.value,
                "children": list(
                    Dictionary.objects.filter(parent=instance.id)
                    .filter(status=1)
                    .values("label", "value", "type", "color")
                ),
            }
        )
    return {ele.get("value"): ele for ele in data}
def _get_all_system_config():
    data = {}
    from dvadmin.system.models import SystemConfig
    system_config_obj = (
        SystemConfig.objects.filter(parent_id__isnull=False)
        .values("parent__key", "key", "value", "form_item_type")
        .order_by("sort")
    )
    for system_config in system_config_obj:
        value = system_config.get("value", "")
        if value and system_config.get("form_item_type") == 7:
            value = value[0].get("url")
        if value and system_config.get("form_item_type") == 11:
            new_value = []
            for ele in value:
                new_value.append({
                    "key": ele.get('key'),
                    "title": ele.get('title'),
                    "value": ele.get('value'),
                })
            new_value.sort(key=lambda s: s["key"])
            value = new_value
        data[f"{system_config.get('parent__key')}.{system_config.get('key')}"] = value
    return data
def init_dictionary():
    try:
        if is_tenants_mode():
            from django_tenants.utils import tenant_context, get_tenant_model
            for tenant in get_tenant_model().objects.filter():
                with tenant_context(tenant):
                    settings.DICTIONARY_CONFIG[connection.tenant.schema_name] = _get_all_dictionary()
        else:
            settings.DICTIONARY_CONFIG = _get_all_dictionary()
    except Exception as e:
        print("请先进行数据库迁移!")
    return
def init_system_config():
    try:
        if is_tenants_mode():
            from django_tenants.utils import tenant_context, get_tenant_model
            for tenant in get_tenant_model().objects.filter():
                with tenant_context(tenant):
                    settings.SYSTEM_CONFIG[connection.tenant.schema_name] = _get_all_system_config()
        else:
            settings.SYSTEM_CONFIG = _get_all_system_config()
    except Exception as e:
        print("请先进行数据库迁移!")
    return
def refresh_dictionary():
    if is_tenants_mode():
        from django_tenants.utils import tenant_context, get_tenant_model
        for tenant in get_tenant_model().objects.filter():
            with tenant_context(tenant):
                settings.DICTIONARY_CONFIG[connection.tenant.schema_name] = _get_all_dictionary()
    else:
        settings.DICTIONARY_CONFIG = _get_all_dictionary()
def refresh_system_config():
    if is_tenants_mode():
        from django_tenants.utils import tenant_context, get_tenant_model
        for tenant in get_tenant_model().objects.filter():
            with tenant_context(tenant):
                settings.SYSTEM_CONFIG[connection.tenant.schema_name] = _get_all_system_config()
    else:
        settings.SYSTEM_CONFIG = _get_all_system_config()
def get_dictionary_config(schema_name=None):
    if not settings.DICTIONARY_CONFIG:
        refresh_dictionary()
    if is_tenants_mode():
        dictionary_config = settings.DICTIONARY_CONFIG[schema_name or connection.tenant.schema_name]
    else:
        dictionary_config = settings.DICTIONARY_CONFIG
    return dictionary_config or {}
def get_dictionary_values(key, schema_name=None):
    dictionary_config = get_dictionary_config(schema_name)
    return dictionary_config.get(key)
def get_dictionary_label(key, name, schema_name=None):
    children = get_dictionary_values(key, schema_name) or []
    for ele in children:
        if ele.get("value") == str(name):
            return ele.get("label")
    return ""
def get_system_config(schema_name=None):
    if not settings.SYSTEM_CONFIG:
        refresh_system_config()
    if is_tenants_mode():
        dictionary_config = settings.SYSTEM_CONFIG[schema_name or connection.tenant.schema_name]
    else:
        dictionary_config = settings.SYSTEM_CONFIG
    return dictionary_config or {}
def get_system_config_values(key, schema_name=None):
    system_config = get_system_config(schema_name)
    return system_config.get(key)
def get_system_config_label(key, name, schema_name=None):
    children = get_system_config_values(key, schema_name) or []
    for ele in children:
        if ele.get("value") == str(name):
            return ele.get("label")
    return ""