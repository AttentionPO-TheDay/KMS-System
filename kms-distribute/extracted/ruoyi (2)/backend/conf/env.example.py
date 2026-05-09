import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_ENGINE = "django.db.backends.sqlite3"
DATABASE_NAME = os.path.join(BASE_DIR, "db.sqlite3")
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 3306
DATABASE_USER = "root"
DATABASE_PASSWORD = "123456"
TABLE_PREFIX = "dvadmin_"
DEBUG = True
ENABLE_LOGIN_ANALYSIS_LOG = True
LOGIN_NO_CAPTCHA_AUTH = True
ALLOWED_HOSTS = ["*"]
COLUMN_EXCLUDE_APPS = []