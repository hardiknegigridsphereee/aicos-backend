# timetable/utils.py
from django.db.models import Q
from academics.models import StudentEnrollment, TeacherAssignment


def get_student_current_section(student_profile):
    """
    Get the current section and academic year for a student.
    Returns (section, academic_year) or (None, None).
    """
    enrollment = StudentEnrollment.objects.filter(
        student=student_profile
    ).order_by('-academic_year__start_date').first()
    
    if enrollment:
        return enrollment.section, enrollment.academic_year
    return None, None


def get_teacher_sections(teacher_profile, academic_year=None):
    """
    Get all sections a teacher is assigned to for a given academic year.
    Returns a queryset of sections.
    """
    from academics.models import Section
    
    assignments = TeacherAssignment.objects.filter(
        teacher=teacher_profile,
    )
    
    if academic_year:
        assignments = assignments.filter(academic_year=academic_year)
    
    return Section.objects.filter(
        id__in=assignments.values_list('section_id', flat=True)
    ).distinct()


def get_student_timetable(student_profile, academic_year=None):
    """
    Get the full timetable for a student.
    Returns a queryset of TimetableEntry objects.
    """
    from .models import TimetableEntry
    
    section, year = get_student_current_section(student_profile)
    
    if not section:
        return TimetableEntry.objects.none()
    
    if not academic_year:
        academic_year = year
    
    return TimetableEntry.objects.filter(
        section=section,
        academic_year=academic_year,
        is_active=True
    ).select_related('class_level', 'section', 'subject', 'teacher__user', 'time_slot')


def get_teacher_timetable(teacher_profile, academic_year=None):
    """
    Get the full timetable for a teacher.
    Returns a queryset of TimetableEntry objects.
    """
    from .models import TimetableEntry
    
    qs = TimetableEntry.objects.filter(
        teacher=teacher_profile,
        is_active=True
    ).select_related('class_level', 'section', 'subject', 'teacher__user', 'time_slot')
    
    if academic_year:
        qs = qs.filter(academic_year=academic_year)
    
    return qs


def get_section_timetable(section, academic_year):
    """
    Get the timetable for a specific section.
    """
    from .models import TimetableEntry
    
    return TimetableEntry.objects.filter(
        section=section,
        academic_year=academic_year,
        is_active=True
    ).select_related('class_level', 'section', 'subject', 'teacher__user', 'time_slot')


def get_class_timetable(class_level, academic_year):
    """
    Get the timetable for all sections of a class level.
    """
    from .models import TimetableEntry
    
    return TimetableEntry.objects.filter(
        class_level=class_level,
        academic_year=academic_year,
        is_active=True
    ).select_related('class_level', 'section', 'subject', 'teacher__user', 'time_slot')


def check_conflicts(entries):
    """
    Check for conflicts in a list of timetable entries.
    Returns a list of conflict dicts.
    """
    conflicts = []
    
    # Check for teacher conflicts (teacher at same time)
    teacher_slots = {}
    for entry in entries:
        key = (entry.teacher_id, entry.time_slot_id)
        if key in teacher_slots:
            conflicts.append({
                'type': 'teacher_conflict',
                'message': f"Teacher {entry.teacher} is assigned to two classes at the same time.",
                'details': {
                    'teacher_id': str(entry.teacher_id),
                    'time_slot_id': str(entry.time_slot_id),
                    'entry1': str(teacher_slots[key].id),
                    'entry2': str(entry.id)
                }
            })
        teacher_slots[key] = entry
    
    # Check for section conflicts (section at same time)
    section_slots = {}
    for entry in entries:
        key = (entry.section_id, entry.time_slot_id)
        if key in section_slots:
            conflicts.append({
                'type': 'section_conflict',
                'message': f"Section {entry.section} has two classes at the same time.",
                'details': {
                    'section_id': str(entry.section_id),
                    'time_slot_id': str(entry.time_slot_id),
                    'entry1': str(section_slots[key].id),
                    'entry2': str(entry.id)
                }
            })
        section_slots[key] = entry
    
    return conflicts


def organize_timetable_by_day(entries):
    """
    Organize timetable entries by day and period for easy display.
    Returns a dictionary: {day: {period: entry}}
    """
    from .models import TimeSlot
    
    timetable = {}
    days = dict(TimeSlot.DAY_CHOICES).keys()
    
    # Initialize all days with empty dicts
    for day in days:
        timetable[day] = {}
    
    for entry in entries:
        day = entry.time_slot.day
        period = entry.time_slot.period_number
        if day not in timetable:
            timetable[day] = {}
        timetable[day][period] = entry
    
    return timetable


def generate_time_slots_from_settings(timetable_settings, academic_year):
    """
    Generate TimeSlot objects from TimetableSettings.
    Returns a list of TimeSlot instances.
    """
    from .models import TimeSlot
    from datetime import datetime, timedelta
    
    time_slots = []
    working_days = timetable_settings.get_working_days_list()
    period_times = timetable_settings.get_period_times()
    
    for day in working_days:
        for period in period_times:
            time_slots.append(
                TimeSlot(
                    school=timetable_settings.school,
                    academic_year=academic_year,
                    day=day,
                    start_time=datetime.strptime(period['start_time'], '%H:%M:%S').time(),
                    end_time=datetime.strptime(period['end_time'], '%H:%M:%S').time(),
                    period_number=period['period_number'],
                    is_break=period['is_break'],
                    break_name=period['break_name']
                )
            )
    
    return time_slots