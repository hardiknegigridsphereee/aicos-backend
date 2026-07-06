# notifications/urls.py
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet

router = DefaultRouter()
router.register(r'', NotificationViewSet, basename='notification')

# GET  /api/v1/notifications/
# GET  /api/v1/notifications/{id}/
# GET  /api/v1/notifications/unread-count/
# POST /api/v1/notifications/{id}/mark-read/
# POST /api/v1/notifications/mark-all-read/
urlpatterns = [
    path('', include(router.urls)),
]
