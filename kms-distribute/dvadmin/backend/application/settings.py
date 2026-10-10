import os
import sys
from pathlib import Path
from datetime import timedelta
BASE_DIR = Path(__file__).resolve().parent.parent
from conf.env import *
SECRET_KEY = "django-insecure--z8%exyzt7e_%i@1+#1mm=%lb5=^fx_57=1@a+_y7bg5-w%)sm"
PLUGINS_PATH = os.path.join(BASE_DIR, "plugins")
sys.path.insert(0, os.path.join(PLUGINS_PATH))
[
    sys.path.insert(0, os.path.join(PLUGINS_PATH, ele))
    for ele in os.listdir(PLUGINS_PATH)
    if os.path.isdir(os.path.join(PLUGINS_PATH, ele)) and not ele.startswith("__")
]
DEBUG = locals().get("DEBUG", True)
ALLOWED_HOSTS = locals().get("ALLOWED_HOSTS", ["*"])
# Django runs behind the KMS Nginx gateway. The gateway overwrites this header
# from its own listener scheme; direct backend ports are not published.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
COLUMN_EXCLUDE_APPS = ['channels', 'captcha'] + locals().get("COLUMN_EXCLUDE_APPS", [])
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_comment_migrate",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "drf_yasg",
    "captcha",
    "channels",
    "dvadmin.system",
    "pqkds",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "pqkds.demo_context.DemoContextMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dvadmin.utils.middleware.ApiLoggingMiddleware",
]
ROOT_URLCONF = "application.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "application.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": DATABASE_ENGINE,
        "NAME": DATABASE_NAME,
        "USER": DATABASE_USER,
        "PASSWORD": DATABASE_PASSWORD,
        "HOST": DATABASE_HOST,
        "PORT": DATABASE_PORT,
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            "charset": "utf8mb4",
            "connect_timeout": 60,
            "read_timeout": 600,
            "write_timeout": 600,
        },
        "CONN_MAX_AGE": 0,
    }
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
AUTH_USER_MODEL = "system.Users"
USERNAME_FIELD = "username"
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]
LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_L10N = True
USE_TZ = False

# ---------------------------------------------------------------------------
# 缓存（Redis）
# ---------------------------------------------------------------------------
# 为什么必须显式配置，不能用 Django 默认的 LocMemCache：
#   节点设备凭据登录要用一次性 **挑战**（`node_auth_views`）。挑战先在
#   `challenge` 端点写入、再到 `login` 端点读出核销。而本服务以
#   **gunicorn workers=2**（见 gunicorn_conf.py）运行 —— 默认的 LocMemCache
#   **是每个 worker 各一份**，两个请求落到不同 worker 时挑战就"查不到"。
#   表现为登录随机失败，且重试可能又成功，极难定位。
#
# 用同一套 kms_redis（compose 已在网络里，服务名 kms_redis）。
# 连接串可用环境变量覆盖，便于本地不开 compose 时改指本机 redis。
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_URL", "redis://kms_redis:6379/2"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # 连接不上时**明确报错**，不要静默退化成"没有缓存"——
            # 那会让挑战验证看起来像"挑战不存在"，把部署故障伪装成登录失败。
            "IGNORE_EXCEPTIONS": False,
        },
        "KEY_PREFIX": "pqkds",
    }
}

STATIC_URL = "/static/"
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "static"),
]
MEDIA_ROOT = "media"
MEDIA_URL = "/media/"
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]
ASGI_APPLICATION = 'application.asgi.application'
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}
SERVER_LOGS_FILE = os.path.join(BASE_DIR, "logs", "server.log")
ERROR_LOGS_FILE = os.path.join(BASE_DIR, "logs", "error.log")
LOGS_FILE = os.path.join(BASE_DIR, "logs")
if not os.path.exists(os.path.join(BASE_DIR, "logs")):
    os.makedirs(os.path.join(BASE_DIR, "logs"))
STANDARD_LOG_FORMAT = (
    "[%(asctime)s][%(name)s.%(funcName)s():%(lineno)d] [%(levelname)s] %(message)s"
)
CONSOLE_LOG_FORMAT = (
    "[%(asctime)s][%(name)s.%(funcName)s():%(lineno)d] [%(levelname)s] %(message)s"
)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ignore_ws_404": {
            "()": "dvadmin.utils.log_filters.IgnoreWs404Filter",
        },
    },
    "formatters": {
        "standard": {"format": STANDARD_LOG_FORMAT},
        "console": {
            "format": CONSOLE_LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "file": {
            "format": CONSOLE_LOG_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": SERVER_LOGS_FILE,
            "maxBytes": 1024 * 1024 * 100,
            "backupCount": 5,
            "formatter": "standard",
            "encoding": "utf-8",
        },
        "error": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": ERROR_LOGS_FILE,
            "maxBytes": 1024 * 1024 * 100,
            "backupCount": 3,
            "formatter": "standard",
            "encoding": "utf-8",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "console",
            "filters": ["ignore_ws_404"],
        },
    },
    "loggers": {
        "": {
            "handlers": ["console", "error", "file"],
            "level": "INFO",
        },
        "django": {
            "handlers": ["console", "error", "file"],
            "level": "INFO",
            "propagate": False,
        },
        'django.db.backends': {
            'handlers': ["console", "error", "file"],
            'propagate': False,
            'level': "INFO"
        },
        "uvicorn.error": {
            "level": "INFO",
            "handlers": ["console", "error", "file"],
        },
        "uvicorn.access": {
            "handlers": ["console", "error", "file"],
            "level": "INFO"
        },
    },
}
REST_FRAMEWORK = {
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.MultiPartParser',
    ),
    "DATETIME_FORMAT": "%Y-%m-%d %H:%M:%S",
    "DATE_FORMAT": "%Y-%m-%d",
    "DEFAULT_FILTER_BACKENDS": (
        "dvadmin.utils.filters.CustomDjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "dvadmin.utils.pagination.CustomPagination",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "dvadmin.utils.exception.CustomExceptionHandler",
}
AUTHENTICATION_BACKENDS = ["dvadmin.utils.backends.CustomBackend"]
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=1440),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("JWT",),
    "ROTATE_REFRESH_TOKENS": True,
}
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {"basic": {"type": "basic"}},
    "LOGIN_URL": "apiLogin/",
    "LOGOUT_URL": "rest_framework:logout",
    "APIS_SORTER": "alpha",
    "JSON_EDITOR": True,
    "OPERATIONS_SORTER": "alpha",
    "VALIDATOR_URL": None,
    "AUTO_SCHEMA_TYPE": 2,
    "DEFAULT_AUTO_SCHEMA_CLASS": "dvadmin.utils.swagger.CustomSwaggerAutoSchema",
}
CAPTCHA_IMAGE_SIZE = (160, 46)
CAPTCHA_LENGTH = 4
CAPTCHA_TIMEOUT = 1
CAPTCHA_OUTPUT_FORMAT = "%(image)s %(text_field)s %(hidden_field)s "
CAPTCHA_FONT_SIZE = 36
CAPTCHA_FOREGROUND_COLOR = "#64DAAA"
CAPTCHA_BACKGROUND_COLOR = "#F5F7F4"
CAPTCHA_NOISE_FUNCTIONS = (
    "captcha.helpers.noise_arcs",
)
CAPTCHA_CHALLENGE_FUNCT = "captcha.helpers.math_challenge"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
API_LOG_ENABLE = True
API_LOG_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]  # 记录所有操作方法
API_MODEL_MAP = {
    "/token/": "登录模块",
    "/api/login/": "登录模块",
    "/api/plugins_market/plugins/": "插件市场",
    # PQKDS 模块
    "/api/pqkds/system-parameters/initialize/": "系统参数",
    "/api/pqkds/system-parameters/generate_kyber_partial_key/": "KGC密钥生成",
    "/api/pqkds/system-parameters/generate_falcon_partial_key/": "KGC密钥生成",
    "/api/pqkds/system-parameters/generate_all_partial_keys/": "KGC密钥生成",
    "/api/pqkds/nodes/register/": "节点管理",
    "/api/pqkds/nodes/batch_delete/": "节点管理",
    "/api/pqkds/session-keys/initiate/": "会话管理",
    "/api/pqkds/session-keys/verify_and_decrypt/": "会话管理",
    "/api/pqkds/blockchain-config/deploy_contract/": "区块链管理",
    "/api/pqkds/blockchain-config/sync_database_to_blockchain/": "区块链管理",
    "/api/pqkds/node/generate-falcon-keypair/": "密钥生成",
    "/api/pqkds/node/save-falcon-keys/": "密钥管理",
}
DJANGO_CELERY_BEAT_TZ_AWARE = False
CELERY_TIMEZONE = "Asia/Shanghai"
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-sessions': {
        'task': 'pqkds.session_expiration_tasks.cleanup_expired_sessions_task',
        'schedule': crontab(minute=0),
    },
    'validate-active-sessions': {
        'task': 'pqkds.session_expiration_tasks.validate_all_active_sessions_task',
        'schedule': crontab(minute='*/30'),
    },
}
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
ALL_MODELS_OBJECTS = []
INITIALIZE_LIST = []
INITIALIZE_RESET_LIST = []
TABLE_PREFIX = locals().get('TABLE_PREFIX', "")
SYSTEM_CONFIG = {}
DICTIONARY_CONFIG = {}
TENANT_SHARED_APPS = []
PLUGINS_URL_PATTERNS = []
