from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoleViewSet, UserRoleViewSet, PermissionViewSet, ChangePasswordView

router = DefaultRouter()
router.register(r'permissions', PermissionViewSet, basename='permission')
router.register(r'roles', RoleViewSet, basename='role')
router.register(r'user-roles', UserRoleViewSet, basename='userrole')

urlpatterns = [
    path('', include(router.urls)),
    # Password Management
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
