# accounts/permissions.py
from rest_framework import permissions
from profiles.models import StudentProfile, TeacherProfile, ParentProfile

def HasModulePermission(module_name, action_type):
    """
    A Class Factory that dynamically generates a DRF Permission class.
    
    Usage in a ViewSet:
        permission_classes = [HasModulePermission('Attendance', 'write')]
        
    Args:
        module_name (str): The module being accessed (e.g., 'Attendance', 'Grades').
        action_type (str): The type of action (e.g., 'read', 'write', 'delete').
    """
    class _HasModulePermission(permissions.BasePermission):
        
        def has_permission(self, request, view):
            # 1. Unauthenticated users are immediately rejected
            if not request.user or not request.user.is_authenticated:
                return False

            # 2. Global Admins (Superusers) bypass all RBAC checks
            if request.user.is_superuser:
                return True

            # 3. Construct the codename we are looking for (e.g., 'attendance.write')
            required_codename = f"{module_name.lower()}.{action_type.lower()}"

            # 4. Check if the user has any role in their current school 
            #    that contains this specific permission codename.
            has_permission = request.user.user_roles.filter(
                school=request.user.school,
                role__permissions__codename=required_codename
            ).exists()

            return has_permission
            
    return _HasModulePermission


class IsStudent(permissions.BasePermission):
    """
    Permission class to check if user has a StudentProfile.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Superusers bypass
        if request.user.is_superuser:
            return True
        
        # Check if user has a student profile
        return StudentProfile.objects.filter(user=request.user).exists()

    def has_object_permission(self, request, view, obj):
        # Check if the student is accessing their own data
        if hasattr(obj, 'student') and hasattr(obj.student, 'user'):
            return obj.student.user == request.user
        if hasattr(obj, 'user') and hasattr(obj, 'user') == request.user:
            return obj.user == request.user
        return False


class IsTeacher(permissions.BasePermission):
    """
    Permission class to check if user has a TeacherProfile.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        return TeacherProfile.objects.filter(user=request.user).exists()


class IsParent(permissions.BasePermission):
    """
    Permission class to check if user has a ParentProfile.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        return ParentProfile.objects.filter(user=request.user).exists()


class IsStudentOrReadOnly(permissions.BasePermission):
    """
    Allow students to read their own data, but only teachers/admins can modify.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        # Allow read-only for everyone
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Only students can modify their own data
        return StudentProfile.objects.filter(user=request.user).exists()


class IsTeacherOrStaff(permissions.BasePermission):
    """
    Allow teachers and staff to access, reject others.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser or request.user.is_staff:
            return True
        
        return TeacherProfile.objects.filter(user=request.user).exists()


class IsParentOfStudent(permissions.BasePermission):
    """
    Check if the logged-in parent is mapped to the student they're trying to access.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        # Check if user is a parent
        try:
            parent = ParentProfile.objects.get(user=request.user)
        except ParentProfile.DoesNotExist:
            return False
        
        # For list views, check if there's a student_id param
        student_id = request.query_params.get('student_id')
        if student_id:
            from profiles.models import ParentStudentMapping
            return ParentStudentMapping.objects.filter(
                parent=parent,
                student_id=student_id
            ).exists()
        
        # For detail views, will check object permission
        return True

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        
        try:
            parent = ParentProfile.objects.get(user=request.user)
        except ParentProfile.DoesNotExist:
            return False
        
        from profiles.models import ParentStudentMapping
        
        # Check if the object has a student field
        if hasattr(obj, 'student'):
            return ParentStudentMapping.objects.filter(
                parent=parent,
                student=obj.student
            ).exists()
        
        # Check if the object itself is a student
        if hasattr(obj, 'user') and hasattr(obj, 'enrollment_number'):
            return ParentStudentMapping.objects.filter(
                parent=parent,
                student=obj
            ).exists()
        
        return False