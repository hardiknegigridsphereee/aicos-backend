# timetable/models.py
import uuid
from django.db import models
from django.core.exceptions import ValidationError
from tenants.models import TenantAwareModel


class TimeSlot(TenantAwareModel):
    """
    Defines time slots for the school day.
    These are auto-generated based on TimetableSettings.
    """
    DAY_CHOICES = [
        ('Monday', 'Monday'),
        ('Tuesday', 'Tuesday'),
        ('Wednesday', 'Wednesday'),
        ('Thursday', 'Thursday'),
        ('Friday', 'Friday'),
        ('Saturday', 'Saturday'),
        ('Sunday', 'Sunday'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    day = models.CharField(max_length=20, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    period_number = models.IntegerField(help_text="Period number in the day (1, 2, 3, ...)")
    
    # Optional: Break/Lunch periods
    is_break = models.BooleanField(default=False)
    break_name = models.CharField(max_length=50, blank=True, null=True)
    
    # Link to academic year
    academic_year = models.ForeignKey(
        'academics.AcademicYear',
        on_delete=models.CASCADE,
        related_name='time_slots'
    )
    
    class Meta:
        ordering = ['day', 'period_number']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'day', 'period_number', 'academic_year'],
                name='unique_school_day_period_year'
            )
        ]

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError("End time must be after start time.")

    def __str__(self):
        day_display = dict(self.DAY_CHOICES).get(self.day, self.day)
        return f"{day_display} - Period {self.period_number}: {self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"


class TimetableEntry(TenantAwareModel):
    """
    A single entry in the timetable.
    Maps a class, section, subject, teacher to a specific time slot.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # What is being taught
    class_level = models.ForeignKey(
        'academics.ClassLevel',
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    section = models.ForeignKey(
        'academics.Section',
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    subject = models.ForeignKey(
        'academics.Subject',
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    teacher = models.ForeignKey(
        'profiles.TeacherProfile',
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    
    # When it is taught
    time_slot = models.ForeignKey(
        TimeSlot,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    academic_year = models.ForeignKey(
        'academics.AcademicYear',
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    
    # Additional info
    room_number = models.CharField(max_length=20, blank=True, null=True)
    notes = models.CharField(max_length=255, blank=True, null=True)
    
    # Soft delete
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'tenants.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timetable_entries_created'
    )

    class Meta:
        ordering = ['class_level__numeric_order', 'section__name', 'time_slot__day', 'time_slot__period_number']
        constraints = [
            # A teacher cannot be in two places at once
            models.UniqueConstraint(
                fields=['school', 'teacher', 'time_slot'],
                name='unique_teacher_per_time_slot'
            ),
            # A section cannot have two subjects at the same time
            models.UniqueConstraint(
                fields=['school', 'section', 'time_slot'],
                name='unique_section_per_time_slot'
            ),
        ]
        indexes = [
            models.Index(fields=['class_level', 'section', 'academic_year']),
            models.Index(fields=['teacher', 'time_slot']),
        ]

    def clean(self):
        # Validate that the class_level matches the section's class_level
        if self.section and self.class_level and self.section.class_level != self.class_level:
            raise ValidationError("Section does not belong to the selected class level.")

    def __str__(self):
        return f"{self.class_level.name} - {self.section.name} | {self.subject.name} | {self.time_slot}"


class TimetableTemplate(TenantAwareModel):
    """
    Pre-defined timetable template that can be saved and applied.
    Useful for schools that want to reuse timetable structures.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    academic_year = models.ForeignKey(
        'academics.AcademicYear',
        on_delete=models.CASCADE,
        related_name='timetable_templates'
    )
    
    # Template data stored as JSON for easy copy
    data = models.JSONField(default=dict, help_text="Stores the template structure")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'tenants.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'name', 'academic_year'],
                name='unique_template_name_per_year'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"