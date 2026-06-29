from .base import *

# Ensure DEBUG is True for local development
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*']

# ------------------------------------------------------------------------
# DATABASE CONFIGURATION (Supabase / PostgreSQL)
# ------------------------------------------------------------------------
DATABASES = {
    'default': env.db('DATABASE_URL')
}

# ------------------------------------------------------------------------
# CORS CONFIGURATION - FULLY CONFIGURED FOR TESTING
# ------------------------------------------------------------------------

# Allow all origins for testing (disable this in production!)
CORS_ALLOW_ALL_ORIGINS = True

# Allow credentials
CORS_ALLOW_CREDENTIALS = True

# Allow all methods
CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

# Allow all headers
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

# Preflight max age
CORS_PREFLIGHT_MAX_AGE = 86400  # 24 hours

# Explicit allowed origins (for when CORS_ALLOW_ALL_ORIGINS is False)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5500",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
    "http://192.168.1.*",
    "http://*.local",
]

# ------------------------------------------------------------------------
# EMAIL CONFIGURATION (Local Testing)
# ------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ------------------------------------------------------------------------
# CSRF CONFIGURATION (For testing)
# ------------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5500",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5500",
]

# Disable CSRF for testing (only for development!)
CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False

# ------------------------------------------------------------------------
# SESSION CONFIGURATION (For testing)
# ------------------------------------------------------------------------
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = False

# ------------------------------------------------------------------------
# SECURITY CONFIGURATION (For testing)
# ------------------------------------------------------------------------
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
