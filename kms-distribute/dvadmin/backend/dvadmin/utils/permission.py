import re
from django.contrib.auth.models import AnonymousUser
from django.db.models import F
from rest_framework.permissions import BasePermission
from dvadmin.system.models import ApiWhiteList, RoleMenuButtonPermission
def ValidationApi(reqApi, validApi):
    if validApi is not None:
        valid_api = validApi.replace('{id}', '.*?')
        matchObj = re.match(valid_api, reqApi, re.M | re.I)
        if matchObj:
            return True
        else:
            return False
    else:
        return False
class AnonymousUserPermission(BasePermission):
    def has_permission(self, request, view):
        if isinstance(request.user, AnonymousUser):
            return False
        return True
def ReUUID(api):
    pattern = re.compile(r'[a-f\d]{4}(?:[a-f\d]{4}-){4}[a-f\d]{12}/$')
    m = pattern.search(api)
    if m:
        res = api.replace(m.group(0), ".*/")
        return res
    else:
        return None
class CustomPermission(BasePermission):
    def has_permission(self, request, view):
        if isinstance(request.user, AnonymousUser):
            return False
        if request.user.is_superuser:
            return True
        else:
            api = request.path
            method = request.method
            methodList = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'PATCH']
            method = methodList.index(method)
            api_white_list = ApiWhiteList.objects.values(permission__api=F('url'), permission__method=F('method'))
            api_white_list = [
                str(item.get('permission__api').replace('{id}', '([a-zA-Z0-9-]+)')) + ":" + str(
                    item.get('permission__method')) + '$' for item in api_white_list if item.get('permission__api')]
            if not hasattr(request.user, "role"):
                return False
            role_id_list = request.user.role.values_list('id',flat=True)
            userApiList = RoleMenuButtonPermission.objects.filter(role__in=role_id_list).values(permission__api=F('menu_button__api'), permission__method=F('menu_button__method'))
            ApiList = [
                str(item.get('permission__api').replace('{id}', '([a-zA-Z0-9-]+)')) + ":" + str(
                    item.get('permission__method')) + '$' for item in userApiList if item.get('permission__api')]
            new_api_ist = api_white_list + ApiList
            new_api = api + ":" + str(method)
            for item in new_api_ist:
                matchObj = re.match(item, new_api, re.M | re.I)
                if matchObj is None:
                    continue
                else:
                    return True
            else:
                return False