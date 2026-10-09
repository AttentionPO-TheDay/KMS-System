# -*- coding: utf-8 -*-
"""显式处理公开量 Outbox；不挂到启动钩子，不自动迁移/补锚存量节点。"""
from django.core.management.base import BaseCommand, CommandError

from pqkds.chain_backend import is_fabric_did
from pqkds.chain_binding_service import process_pending_bindings


class Command(BaseCommand):
    help = 'Process Fabric DID bindings explicitly; never falls back to legacy chain'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if not is_fabric_did():
            raise CommandError('Fabric binding worker requires KMS_CHAIN_BACKEND=fabric-did')
        limit = options['limit']
        if limit < 1 or limit > 10000:
            raise CommandError('--limit must be between 1 and 10000')
        result = process_pending_bindings(limit=limit)
        self.stdout.write(str(result))
