"""
Resolves *who* should receive a notification for circular/grievance events,
and builds the payload.
"""

from tenants.models import User
from profiles.models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from academics.models import StudentEnrollment, TeacherAssignment


# ──────────────────────────────────────────────────────────────────────────
# Grievances
# ──────────────────────────────────────────────────────────────────────────

def get_grievance_admins(school):
    """
    Every user who should be *notified* about a new/updated grievance for
    `school`.

    NOTE: this is intentionally narrower than `grievance_views._is_school_admin`,
    which also treats teachers as "admins" for permission-checking purposes
    (e.g. so a teacher assigned to handle grievances can resolve/reject one
    via IsTeacherOrStaff). Notifications are a different concern -- product
    requirement is that grievances are a school-admin-only inbox, so
    teachers must NOT get a bell notification just because they technically
    have permission to manage grievances. Hence we exclude students,
    parents, AND teachers here, leaving only actual school admin / staff
    accounts.
    """
    return User.objects.filter(school=school).exclude(
        id__in=StudentProfile.objects.filter(school=school).values_list('user_id', flat=True)
    ).exclude(
        id__in=ParentProfile.objects.filter(school=school).values_list('user_id', flat=True)
    ).exclude(
        id__in=TeacherProfile.objects.filter(school=school).values_list('user_id', flat=True)
    )


def build_grievance_payload(grievance):
    return {
        'grievance_id': str(grievance.id),
        'title': grievance.title,
        'category': grievance.category,
        'priority': grievance.priority,
        'status': grievance.status,
        'submitted_by_name': grievance.submitted_by.get_full_name() or grievance.submitted_by.email,
        'redirect_module': 'grievance',
    }


# ──────────────────────────────────────────────────────────────────────────
# Circulars
# ──────────────────────────────────────────────────────────────────────────

def get_circular_recipient_users(circular):
    """
    Resolve the actual User accounts (teachers, students, and parents) who
    should be notified for a published circular, honoring
    target_audience + target_class_levels the same way
    circular_views._recipient_queryset does for reads.
    """
    school = circular.school
    audience = circular.target_audience
    class_level_ids = list(circular.target_class_levels.values_list('id', flat=True))

    recipient_ids = set()

    if audience in ('all', 'teachers'):
        teacher_qs = TeacherProfile.objects.filter(school=school)
        if class_level_ids:
            assigned_teacher_ids = TeacherAssignment.objects.filter(
                school=school, class_level_id__in=class_level_ids
            ).values_list('teacher__user_id', flat=True)
            recipient_ids.update(assigned_teacher_ids)
        else:
            recipient_ids.update(teacher_qs.values_list('user_id', flat=True))

    if audience in ('all', 'students'):
        student_qs = StudentProfile.objects.filter(school=school)
        if class_level_ids:
            enrolled_ids = StudentEnrollment.objects.filter(
                school=school, class_level_id__in=class_level_ids
            ).values_list('student__user_id', flat=True)
            recipient_ids.update(enrolled_ids)
        else:
            recipient_ids.update(student_qs.values_list('user_id', flat=True))

    if audience in ('all', 'parents'):
        if class_level_ids:
            child_student_ids = StudentEnrollment.objects.filter(
                school=school, class_level_id__in=class_level_ids
            ).values_list('student_id', flat=True)
            parent_ids = ParentStudentMapping.objects.filter(
                school=school, student_id__in=child_student_ids
            ).values_list('parent__user_id', flat=True)
        else:
            parent_ids = ParentProfile.objects.filter(school=school).values_list('user_id', flat=True)
        recipient_ids.update(parent_ids)

    return User.objects.filter(id__in=recipient_ids)


def build_circular_payload(circular):
    return {
        'circular_id': str(circular.id),
        'title': circular.title,
        'target_audience': circular.target_audience,
        'redirect_module': 'circular',
    }