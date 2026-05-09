import os
import sys
import django
from django.conf import settings
from django.core.management import call_command
from wsgiref.simple_server import make_server
if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "application.settings")
    django.setup()
    call_command('migrate')
    from django.core.wsgi import get_wsgi_application
    application = get_wsgi_application()
    httpd = make_server('127.0.0.1', 8000, application)
    print("Django server running at http://127.0.0.1:8000")
    print("Press Ctrl+C to stop the server")
    httpd.serve_forever()