"""
Resolves "is this teacher the section/class-teacher of this student?"

Uses the existing academics models:
  - StudentEnrollment: student -> (academic_year, class_level, section)
  - TeacherAssignment: teacher -> (academic_year, section, subject, is_class_teacher)

A student's "section teacher" is the TeacherAssignment row with
is_class_teacher=True for the student's current enrollment's
(academic_year, section).
"""

from academics.models import StudentEnrollment, TeacherAssignment
from profiles.models import TeacherProfile


def get_current_enrollment(student_profile):
    """
    The student's enrollment for the active academic year, falling back
    to their most recent enrollment if no year is marked active.
    """
    qs = StudentEnrollment.objects.filter(student=student_profile).select_related(
        'academic_year', 'section'
    )
    active = qs.filter(academic_year__is_active=True).first()
    if active:
        return active
    return qs.order_by('-academic_year__start_date').first()


def is_section_teacher_of_student(user, student_profile):
    """True if `user` is the class/section teacher for `student_profile`'s current section."""
    teacher_profile = TeacherProfile.objects.filter(user=user, school=user.school).first()
    if not teacher_profile:
        return False

    enrollment = get_current_enrollment(student_profile)
    if not enrollment:
        return False

    return TeacherAssignment.objects.filter(
        teacher=teacher_profile,
        school=user.school,
        academic_year=enrollment.academic_year,
        section=enrollment.section,
        is_class_teacher=True,
    ).exists()


def get_homeroom_student_ids(user):
    """
    All StudentProfile ids for which `user` is currently the class/section
    teacher (i.e. is_class_teacher=True for that student's current section
    + academic year). Returns an empty set if `user` isn't a teacher or
    isn't a class teacher of any section.
    """
    teacher_profile = TeacherProfile.objects.filter(user=user, school=user.school).first()
    if not teacher_profile:
        return set()

    assignments = TeacherAssignment.objects.filter(
        teacher=teacher_profile,
        school=user.school,
        is_class_teacher=True,
    ).values_list('academic_year_id', 'section_id')

    if not assignments:
        return set()

    student_ids = set()
    for academic_year_id, section_id in assignments:
        ids = StudentEnrollment.objects.filter(
            academic_year_id=academic_year_id,
            section_id=section_id,
        ).values_list('student_id', flat=True)
        student_ids.update(ids)

    return student_ids
