from django.core.management.base import BaseCommand

from pqkds.auto_revoke_service import run_forever, run_once


class Command(BaseCommand):
    help = 'Continuously inspect and revoke severely abnormal node keys.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        if options['once']:
            self.stdout.write(str(run_once()))
        else:
            run_forever()
