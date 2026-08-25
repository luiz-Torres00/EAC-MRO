"""
Django settings — EAC MRO Backend
Stack: Django 4.2 + DRF + SimpleJWT + PostgreSQL (Railway)
"""
import os
from pathlib import Path
import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ── Apps ────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    # Local
    'accounts',
    'pedidos',
    'produtos',
    'notificacoes',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'eac_mro.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'eac_mro.wsgi.application'

# ── Banco de dados ───────────────────────────────────────────────────────────
# Railway injeta DATABASE_URL automaticamente
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
    )
}

# ── Autenticação customizada ─────────────────────────────────────────────────
AUTH_USER_MODEL = 'accounts.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ── DRF ─────────────────────────────────────────────────────────────────────
# Sem paginação automática do DRF: o frontend Vue já faz sua própria paginação
# client-side (componente Paginacao.vue) e espera receber a lista completa
# como array puro em cada endpoint de listagem — não o envelope
# {count, next, previous, results} que o PageNumberPagination geraria.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# ── JWT ──────────────────────────────────────────────────────────────────────
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS':  True,
    'AUTH_HEADER_TYPES':      ('Bearer',),
}

# ── CORS ─────────────────────────────────────────────────────────────────────
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:5173,http://localhost:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# ── Internacionalização ──────────────────────────────────────────────────────
LANGUAGE_CODE = 'pt-br'
TIME_ZONE     = 'America/Sao_Paulo'
USE_I18N      = True
USE_TZ        = True

# ── Arquivos estáticos ───────────────────────────────────────────────────────
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ── E-mail ───────────────────────────────────────────────────────────────────
# Sem EMAIL_HOST configurado (padrão em dev), os e-mails só são impressos no
# terminal do runserver — não quebra nada enquanto não tivermos as credenciais
# reais de SMTP. Pra ligar o envio de verdade, defina no .env: EMAIL_HOST,
# EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD (ex.: Gmail com senha de
# app, SendGrid, Mailgun, etc.) e EMAIL_USE_TLS=True.
if os.environ.get('EMAIL_HOST'):
    EMAIL_BACKEND       = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST          = os.environ.get('EMAIL_HOST')
    EMAIL_PORT          = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER     = os.environ.get('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS       = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'EAC MRO <nao-responda@mro.com>')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
