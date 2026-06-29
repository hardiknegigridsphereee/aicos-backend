import os
from pathlib import Path
from datetime import timedelta
import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# Since base.py is inside `core/settings/`, we need to go up 3 levels to reach the project root.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environ to read .env file
env = environ.Env(
    DEBUG=(bool, False)
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('DJANGO_SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = []

# Application definition
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',  # For JWT Authentication later
    'drf_spectacular',           # OpenAPI / Swagger UI generator
    'corsheaders',               # To handle requests from your frontend
    'django_filters', 
    'storages'           # ← ADDED: for is_archived and class_level filtering
]

# We will create these apps as we progress through the roadmap
LOCAL_APPS = [
    'tenants',        # Global core, Auth, and Tenant (School) foundation
    'accounts',       # RBAC (Roles, Permissions)
    'profiles',     # Student, Teacher, Parent profiles
    'academics',    # Classes, Sections, Enrollments
    'operations',
    'school_admin',
    'tutor',  # Dashboard, Notifications, Activity Logs
    # 'finance',      # Invoices, Payments
    'leave_management',
    'timetable'
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ------------------------------------------------------------------------
# AUTHENTICATION
# ------------------------------------------------------------------------
AUTH_USER_MODEL = 'tenants.User' 

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware', # Ensure this is high up
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
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

WSGI_APPLICATION = 'core.wsgi.application'

# Password validation
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

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_URL = 'media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ------------------------------------------------------------------------
# DJANGO REST FRAMEWORK CONFIGURATION
# ------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [                                          # ← ADDED
        'django_filters.rest_framework.DjangoFilterBackend',              # ← ADDED
        'rest_framework.filters.SearchFilter',                            # ← ADDED
    ],  
}

# ------------------------------------------------------------------------
# SIMPLE JWT CONFIGURATION
# ------------------------------------------------------------------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ------------------------------------------------------------------------
# DRF SPECTACULAR (SWAGGER/OPENAPI) CONFIGURATION
# ------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'Multi-Tenant School ERP API',
    'DESCRIPTION': 'Robust Multi-Tenant backend for School Management operations.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True, # Good for handling complex nested serializers
    'SECURITY': [{'jwtAuth': []}],
}

# ============================================================================
# R2 / S3 COMPATIBLE STORAGE CONFIGURATION
# ============================================================================

# R2 Configuration
R2_ACCOUNT_ID = env('R2_ACCOUNT_ID', default='')
R2_ACCESS_KEY_ID = env('R2_ACCESS_KEY_ID', default='')
R2_SECRET_ACCESS_KEY = env('R2_SECRET_ACCESS_KEY', default='')
R2_BUCKET_NAME = env('R2_BUCKET_NAME', default='')

# S3/R2 Settings
AWS_S3_ENDPOINT_URL = f'https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com' if R2_ACCOUNT_ID else None
AWS_ACCESS_KEY_ID = R2_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY = R2_SECRET_ACCESS_KEY
AWS_STORAGE_BUCKET_NAME = R2_BUCKET_NAME
AWS_S3_REGION_NAME = 'auto'
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_QUERYSTRING_AUTH = True  # ✅ Important: Keep this True for signed URLs
AWS_S3_FILE_OVERWRITE = False

# ✅ IMPORTANT: Do NOT set DEFAULT_ACL for signed URLs
# AWS_DEFAULT_ACL = None  # Let signed URLs handle permissions

# Storage backend
if R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME:
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    MEDIA_URL = f'https://{R2_BUCKET_NAME}.{R2_ACCOUNT_ID}.r2.cloudflarestorage.com/'
    print(f"✅ Using R2 storage: {R2_BUCKET_NAME}")
else:
    DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
    MEDIA_URL = '/media/'
    print("⚠️ Using local storage (R2 not configured)")