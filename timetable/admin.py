# timetable/admin.py
from django.contrib import admin
from .models import TimeSlot, TimetableEntry, TimetableTemplate


@admin.register(TimeSlot)
class TimeSlotAdmin(admin.ModelAdmin):
    list_display = ('day', 'period_number', 'start_time', 'end_time', 'is_break', 'break_name', 'academic_year', 'school')
    list_filter = ('school', 'day', 'is_break', 'academic_year')
    search_fields = ('day', 'break_name')


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = (
        'class_level', 'section', 'subject', 'teacher',
        'time_slot', 'academic_year', 'room_number', 'is_active'
    )
    list_filter = ('school', 'academic_year', 'class_level', 'section', 'is_active')
    search_fields = (
        'class_level__name', 'section__name', 'subject__name',
        'teacher__user__first_name', 'teacher__user__last_name',
        'room_number'
    )
    raw_id_fields = ('class_level', 'section', 'subject', 'teacher', 'time_slot', 'academic_year')


@admin.register(TimetableTemplate)
class TimetableTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'is_active', 'created_at')
    list_filter = ('school', 'academic_year', 'is_active')
    search_fields = ('name', 'description')