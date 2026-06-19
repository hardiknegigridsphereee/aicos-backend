from rest_framework import viewsets, filters
from tenants.views import TenantAwareModelViewSet
from .models import Role, UserRole, Permission
from .serializers import RoleSerializer, UserRoleSerializer, PermissionSerializer


class RoleViewSet(TenantAwareModelViewSet):
    """
    CRUD endpoints for Roles.
    Strictly isolated so admins only see/edit their own school's roles.
    """
    queryset = Role.objects.prefetch_related('permissions').all()
    serializer_class = RoleSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Global Read-Only list of available permissions.
    These are system-wide, so they don't use TenantAwareModelViewSet.
    """
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    pagination_class = None


class UserRoleViewSet(TenantAwareModelViewSet):
    """
    Endpoints for assigning Users to Roles.
    Strictly isolated and validated by the UserRoleSerializer.
    """
    queryset = UserRole.objects.select_related('user', 'role').all()
    serializer_class = UserRoleSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user_id = self.request.query_params.get('user', None)
        role_id = self.request.query_params.get('role', None)

        if user_id:
            qs = qs.filter(user_id=user_id)
        if role_id:
            qs = qs.filter(role_id=role_id)

        return qs