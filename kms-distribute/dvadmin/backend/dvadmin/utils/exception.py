import logging
import traceback
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework.exceptions import APIException as DRFAPIException, AuthenticationFailed, NotAuthenticated
from rest_framework.status import HTTP_401_UNAUTHORIZED
from rest_framework.views import set_rollback, exception_handler
from dvadmin.utils.json_response import ErrorResponse
logger = logging.getLogger(__name__)
class CustomAuthenticationFailed(NotAuthenticated):
    status_code = 400
def CustomExceptionHandler(ex, context):
    msg = ''
    code = 4000
    response = exception_handler(ex, context)
    if isinstance(ex, AuthenticationFailed):
        if response and response.data.get('detail') == "Given token not valid for any token type":
            code = 401
            msg = ex.detail
        elif response and response.data.get('detail') == "Token is blacklisted":
            return ErrorResponse(status=HTTP_401_UNAUTHORIZED)
        else:
            code = 401
            msg = ex.detail
    elif isinstance(ex,Http404):
        code = 400
        msg = "接口地址不正确"
    elif isinstance(ex, DRFAPIException):
        set_rollback()
        msg = ex.detail
        if isinstance(msg,dict):
            for k, v in msg.items():
                for i in v:
                    msg = "%s:%s" % (k, i)
    elif isinstance(ex, ProtectedError):
        set_rollback()
        msg = "删除失败:该条数据与其他数据有相关绑定"
    elif isinstance(ex, Exception):
        logger.exception(traceback.format_exc())
        msg = str(ex)
    return ErrorResponse(msg=msg, code=code)