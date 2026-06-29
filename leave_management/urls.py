from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LeaveRequestViewSet

router = DefaultRouter()
router.register(r'leave-requests', LeaveRequestViewSet, basename='leave-request')

# The @action decorators above add these routes automatically:
#   GET  leave-requests/me/
#   GET  leave-requests/pending-review/
#   POST leave-requests/{id}/approve/
#   POST leave-requests/{id}/reject/
#   POST leave-requests/{id}/cancel/

urlpatterns = [
    path('', include(router.urls)),
]
