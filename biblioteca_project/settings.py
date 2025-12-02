#
# Archivo: biblioteca_project/settings.py
#
from pathlib import Path
import os  

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = 'django-insecure-r)07b179ze38y(7ljrud5uzo3*d@b*uord^tyjbw_yv=dw01k#'


DEBUG = True 


ALLOWED_HOSTS = ["127.0.0.1", "localhost", "fitot.pythonanywhere.com"]

# ─────────────────────────────────────────────────────────────────────
# Apps
# ─────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # terceros
    "rest_framework",
    # apps del proyecto
    "biblioteca",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ─────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "biblioteca_project.urls"

# ─────────────────────────────────────────────────────────────────────
# Templates
# ─────────────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "biblioteca_project.wsgi.application"

# ─────────────────────────────────────────────────────────────────────
# Base de datos (SQLite para localhost)
# ─────────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ─────────────────────────────────────────────────────────────────────
# Internacionalización
# ─────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

# ─────────────────────────────────────────────────────────────────────
# Estáticos (CSS, JS, Avatares predefinidos)
# ─────────────────────────────────────────────────────────────────────
STATIC_URL = "/static/"

# Carpetas donde BUSCA los estáticos en desarrollo
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

#  Carpeta donde RECOLECTA los estáticos para producción ---
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# ─────────────────────────────────────────────────────────────────────
# DRF + JWT (para API)
# ─────────────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.AllowAny",
    ),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CONFIGURACIÓN DE EMAIL (GMAIL SMTP REAL) ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Tus credenciales reales (¡Siempre entre comillas!)
EMAIL_HOST_USER = 'dgacbiblioteca@gmail.com'
EMAIL_HOST_PASSWORD = 'wwhy xfzi nlks gsra'

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# Configuración para archivos subidos por el usuario
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')