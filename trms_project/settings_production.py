"""Production-only profile; the normal local VS Code command is unchanged."""
import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *

DEBUG = False
SECRET_KEY = os.environ.get('TRMS_SECRET_KEY', SECRET_KEY)
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('Production requires a strong TRMS_SECRET_KEY or local key file.')
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('TRMS_ALLOWED_HOSTS', '').split(',') if host.strip()]
if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Set explicit TRMS_ALLOWED_HOSTS for deployment.')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
STATIC_ROOT = BASE_DIR / 'staticfiles'
