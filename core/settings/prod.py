from .base import *

# In production, we usually want this to be False. 
# However, during this initial VPS setup phase, we'll let it read from .env
# so you can see Django error pages if something goes wrong.
DEBUG = env.bool('DEBUG', default=False)

# Read allowed hosts from environment. 
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])

# ------------------------------------------------------------------------
# DATABASE CONFIGURATION (Neon / PostgreSQL)
# ------------------------------------------------------------------------
DATABASES = {
    'default': env.db('DATABASE_URL')
}

# ------------------------------------------------------------------------
# SECURITY CONFIGURATION
# ------------------------------------------------------------------------
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ------------------------------------------------------------------------
# CORS CONFIGURATION - PRODUCTION
# ------------------------------------------------------------------------
# Read from environment, with a fallback for local testing
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True

# Only allow specific methods and headers
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

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

# ------------------------------------------------------------------------
# CSRF TRUSTED ORIGINS
# ------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# ------------------------------------------------------------------------
# STATIC & MEDIA FILES
# ------------------------------------------------------------------------
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
