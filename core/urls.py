# core/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from .views.file_upload_views import (
    GenerateUploadURLView,
    ConfirmUploadView,
    GenerateDownloadURLView,
    GenerateViewURLView,
    GenerateProfileImageUploadURLView,
    GetProfilePictureView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API Routes Base
    path('api/v1/', include('tenants.urls')),
    path('api/v1/profiles/', include('profiles.urls')),
    path('api/v1/academics/', include('academics.urls')),
    path('api/v1/operations/', include('operations.urls')),
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/school-admin/', include('school_admin.urls')),
    path('api/v1/tutor/', include('tutor.urls')),
    
    # File Upload Routes
    path('api/v1/uploads/generate-url/', GenerateUploadURLView.as_view(), name='generate-upload-url'),
    path('api/v1/uploads/confirm/', ConfirmUploadView.as_view(), name='confirm-upload'),
    path('api/v1/uploads/download-url/', GenerateDownloadURLView.as_view(), name='generate-download-url'),
    path('api/v1/uploads/view-url/', GenerateViewURLView.as_view(), name='generate-view-url'),
    
    # Profile image upload & fetch
    path('api/v1/uploads/profile-image/', GenerateProfileImageUploadURLView.as_view(), name='profile-image-upload'),
    path('api/v1/profiles/me/picture/', GetProfilePictureView.as_view(), name='profile-picture'),
    
    # Swagger / OpenAPI Endpoints
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # Leave Management
    path('api/v1/leave-management/', include('leave_management.urls')),
    
    # Timetable Management (NEW)
    path('api/v1/timetable/', include('timetable.urls')),
]

# Serve media files in development (for local storage fallback)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)