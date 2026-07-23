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
# ============================================
# PASSWORD CHANGE VIEW
# ============================================

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

class ChangePasswordView(APIView):
    """
    POST /api/v1/accounts/change-password/
    Allows any authenticated user to change their password.
    Works for ALL roles: Student, Teacher, Parent, Admin
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        # Validate inputs
        if not old_password:
            return Response(
                {'error': 'Current password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not new_password:
            return Response(
                {'error': 'New password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not confirm_password:
            return Response(
                {'error': 'Please confirm your new password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if old password is correct
        if not user.check_password(old_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if new password matches confirmation
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if new password is different from old
        if old_password == new_password:
            return Response(
                {'error': 'New password must be different from current password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate password strength
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response(
                {'error': e.messages},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Change password
        user.set_password(new_password)
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password changed successfully. Please use your new password for subsequent logins.'
        }, status=status.HTTP_200_OK)

# ============================================
# PASSWORD CHANGE VIEW
# ============================================

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

class ChangePasswordView(APIView):
    """
    POST /api/v1/accounts/change-password/
    Allows any authenticated user to change their password.
    Works for ALL roles: Student, Teacher, Parent, Admin
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        user = request.user
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        
        # Validate inputs
        if not old_password:
            return Response(
                {'error': 'Current password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not new_password:
            return Response(
                {'error': 'New password is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not confirm_password:
            return Response(
                {'error': 'Please confirm your new password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if old password is correct
        if not user.check_password(old_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if new password matches confirmation
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if new password is different from old
        if old_password == new_password:
            return Response(
                {'error': 'New password must be different from current password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate password strength
        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            return Response(
                {'error': e.messages},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Change password
        user.set_password(new_password)
        user.save()
        
        return Response({
            'success': True,
            'message': 'Password changed successfully. Please use your new password for subsequent logins.'
        }, status=status.HTTP_200_OK)
