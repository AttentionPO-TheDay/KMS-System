import time
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, transaction
from pqkds.models import NodeLongTermKey
from pqkds.node_fisco_evidence import enabled, enqueue, process_one


class Command(BaseCommand):
    help = 'Automatically process node public registration evidence via Java FISCO (not Web3 or DID)'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--backfill', action='store_true')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if not enabled():
            raise CommandError('KMS_NODE_FISCO_ENABLED must be true with legacy backend')
        if not 1 <= options['limit'] <= 10000:
            raise CommandError('limit must be 1..10000')
        if options['backfill']:
            count = 0
            # Explicit recovery only, never regenerate keys or change their versions.
            for key in NodeLongTermKey.objects.filter(status='ACTIVE').select_related('node').iterator():
                with transaction.atomic():
                    enqueue(key)
                count += 1
            self.stdout.write(f'Queued current registrations: {count}')
        while True:
            close_old_connections()
            for _ in range(options['limit']):
                if not process_one():
                    break
            if not options['loop']:
                break
            time.sleep(5)
