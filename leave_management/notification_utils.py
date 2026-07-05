# leave_management/notification_utils.py
"""
Resolves *who* should receive a notification for a given leave request, and
builds the payload. Kept separate from utils.py (which resolves homeroom
teacher/student relationships) to keep notification concerns isolated.
"""

from tenants.models import User
from profiles.models import ParentProfile, StudentProfile, TeacherProfile

from .utils import get_current_enrollment
from academics.models import TeacherAssignment


def get_school_admin_users(school):
    """
    Every user of `school` who reviews TEACHER leave requests: Django
    staff/superusers plus any account that isn't a student/parent/teacher
    (mirrors leave_management.permissions.is_school_admin, at queryset level).
    """
    return User.objects.filter(school=school).exclude(
        id__in=StudentProfile.objects.filter(school=school).values_list('user_id', flat=True)
    ).exclude(
        id__in=ParentProfile.objects.filter(school=school).values_list('user_id', flat=True)
    ).exclude(
        id__in=TeacherProfile.objects.filter(school=school).values_list('user_id', flat=True)
    )


def get_homeroom_teacher_users(student_profile):
    """Every User who is a class/section teacher for this student's current enrollment."""
    enrollment = get_current_enrollment(student_profile)
    if not enrollment:
        return User.objects.none()

    teacher_ids = TeacherAssignment.objects.filter(
        school=student_profile.school,
        academic_year=enrollment.academic_year,
        section=enrollment.section,
        is_class_teacher=True,
    ).values_list('teacher__user_id', flat=True)

    return User.objects.filter(id__in=teacher_ids)


def get_leave_reviewers(leave_request):
    """
    Who reviews this specific leave request:
      - Teacher applicant -> school admins
      - Student applicant -> that student's homeroom/section teacher(s)
    """
    from .models import LeaveRequest  # local import avoids a circular import at module load

    if leave_request.applicant_role == LeaveRequest.ApplicantRole.TEACHER:
        return get_school_admin_users(leave_request.school)
    return get_homeroom_teacher_users(leave_request.student)


def get_leave_applicant_user(leave_request):
    """The User who should be notified of an approve/reject decision."""
    if leave_request.teacher_id:
        return leave_request.teacher.user
    return leave_request.student.user


def build_leave_payload(leave_request):
    return {
        'leave_id': str(leave_request.id),
        'leave_type': leave_request.leave_type,
        'applicant_role': leave_request.applicant_role,
        'applicant_name': leave_request.applicant_name,
        'start_date': leave_request.start_date.isoformat(),
        'end_date': leave_request.end_date.isoformat(),
        'status': leave_request.status,
        'redirect_module': 'leave-dashboard',
    }
