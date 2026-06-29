from rest_framework import permissions

from profiles.models import ParentProfile, StudentProfile, TeacherProfile


def is_school_admin(user):
    """
    True for superusers, Django staff, and any other authenticated school
    user who isn't a student/parent/teacher (i.e. a school-admin account).
    Shared by the permission class below and by views.py.
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser or user.is_staff:
        return True

    if StudentProfile.objects.filter(user=user).exists():
        return False
    if ParentProfile.objects.filter(user=user).exists():
        return False
    if TeacherProfile.objects.filter(user=user).exists():
        return False

    return bool(user.school)


class IsSchoolAdminOrStaff(permissions.BasePermission):
    """
    Blocks students, parents and teachers from admin-only actions.
    Allows superusers, Django staff, and any other authenticated school
    user who isn't a student/parent/teacher (i.e. school-admin accounts).
    """

    def has_permission(self, request, view):
        return is_school_admin(request.user)


class IsStudentOrTeacher(permissions.BasePermission):
    """Allows any authenticated user who has a Student or Teacher profile."""

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        user = request.user
        if user.is_superuser:
            return True

        return (
            StudentProfile.objects.filter(user=user).exists()
            or TeacherProfile.objects.filter(user=user).exists()
        )
