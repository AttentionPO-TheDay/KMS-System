# -*- coding: utf-8 -*-
"""链后端的唯一选择器；拼错配置不能悄悄落到另一条链上。"""
import os

from django.core.exceptions import ImproperlyConfigured


class NoLegacyWrite(RuntimeError):
    """Fabric 模式不允许初始化带部署/注册副作用的旧链服务。"""


def selected_backend():
    value = os.environ.get('KMS_CHAIN_BACKEND', 'legacy').strip().lower()
    if value not in ('legacy', 'fabric-did'):
        raise ImproperlyConfigured('KMS_CHAIN_BACKEND must be legacy or fabric-did')
    return value


def get_chain_backend():
    return selected_backend()


def is_fabric_did():
    return get_chain_backend() == 'fabric-did'


def require_legacy_backend(operation):
    if is_fabric_did():
        raise NoLegacyWrite(f'{operation}: legacy chain writes are disabled in fabric-did mode')
