from .base import *

# In production, we usually want this to be False. 
# However, during this initial VPS setup phase, we'll let it read from .env
# so you can see Django error pages if something goes wrong.
DEBUG = env.bool('DEBUG', default=False)

# Read allowed hosts from environment. 
# Ensure your .env has ALLOWED_HOSTS=187.127.139.208
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

# IMPORTANT: We are disabling these temporarily. 
# Once you have a Domain Name (e.g., erp.example.com) and an SSL certificate 
# via Certbot/Nginx, you should set these back to True.

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False  # This was likely causing your Timeout!
SECURE_HSTS_SECONDS = 0 
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# ------------------------------------------------------------------------
# CORS CONFIGURATION
# ------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])
CORS_ALLOW_CREDENTIALS = True 
# ------------------------------------------------------------------------
# STATIC & MEDIA FILES
# ------------------------------------------------------------------------
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
# Ensure Whitenoise or Nginx is configured to serve these in production