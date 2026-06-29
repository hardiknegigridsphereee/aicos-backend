# school_admin/models.py
import uuid
from django.db import models
from django.conf import settings
from tenants.models import TenantAwareModel

class ActivityLog(TenantAwareModel):
    """Tracks administrative actions across the school."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=50)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.action_type}] {self.description[:30]}"


class Notification(TenantAwareModel):
    """System alerts and mapping requests for the dashboard."""
    TYPE_CHOICES = (
        ('alert', 'Alert'),
        ('system', 'System'),
        ('mapping', 'Mapping'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default='system')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({'Read' if self.is_read else 'Unread'})"


class SchoolSettings(TenantAwareModel):
    """Stores configurable settings for each school."""
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    grading_scale = models.CharField(max_length=20, default='4.0 GPA')
    attendance_tracking_enabled = models.BooleanField(default=True)
    default_academic_year = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        verbose_name_plural = "School Settings"

    def __str__(self):
        return f"Settings for {self.school.name}"


# ============================================================
# TIMETABLE SETTINGS
# ============================================================

class TimetableSettings(TenantAwareModel):
    """
    Timetable configuration settings for the school.
    ALL fields are required - no defaults. Admin must explicitly set everything.
    """
    class DayChoices(models.TextChoices):
        MONDAY = 'Monday', 'Monday'
        TUESDAY = 'Tuesday', 'Tuesday'
        WEDNESDAY = 'Wednesday', 'Wednesday'
        THURSDAY = 'Thursday', 'Thursday'
        FRIDAY = 'Friday', 'Friday'
        SATURDAY = 'Saturday', 'Saturday'
        SUNDAY = 'Sunday', 'Sunday'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    working_days = models.JSONField(
        help_text="List of working days (e.g., ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'])"
    )
    periods_per_day = models.IntegerField(help_text="Number of periods in a day")
    period_duration = models.IntegerField(help_text="Duration of each period in minutes")
    school_start_time = models.TimeField(help_text="School start time")
    school_end_time = models.TimeField(help_text="School end time")
    lunch_duration = models.IntegerField(help_text="Lunch break duration in minutes")
    lunch_start_after_period = models.IntegerField(help_text="Period number after which lunch occurs")
    max_same_subject_per_day = models.IntegerField(help_text="Maximum periods of same subject per day")
    max_same_subject_per_week = models.IntegerField(help_text="Maximum periods of same subject per week")
    auto_generate = models.BooleanField(default=False, help_text="Enable auto-generation of timetable")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timetable_settings_updated'
    )

    class Meta:
        verbose_name_plural = "Timetable Settings"
        constraints = [
            models.UniqueConstraint(
                fields=['school'],
                name='unique_timetable_settings_per_school'
            )
        ]

    def __str__(self):
        return f"Timetable Settings for {self.school.name}"

    def get_working_days_list(self):
        if isinstance(self.working_days, list):
            return self.working_days
        return []

    def get_total_periods_per_week(self):
        return len(self.get_working_days_list()) * self.periods_per_day

    def get_period_times(self):
        from datetime import datetime, timedelta
        
        start_time = self.school_start_time
        end_time = self.school_end_time
        
        periods = []
        current_time = datetime.combine(datetime.today(), start_time)
        end_datetime = datetime.combine(datetime.today(), end_time)
        
        for period_num in range(1, self.periods_per_day + 1):
            if current_time >= end_datetime:
                break
                
            start_time_obj = current_time.time()
            end_time_calc = current_time + timedelta(minutes=self.period_duration)
            
            is_break = False
            break_name = None
            duration = self.period_duration
            
            if period_num == self.lunch_start_after_period + 1:
                is_break = True
                break_name = 'Lunch Break'
                duration = self.lunch_duration
                end_time_calc = current_time + timedelta(minutes=duration)
            
            if end_time_calc > end_datetime:
                end_time_calc = end_datetime
            
            periods.append({
                'period_number': period_num,
                'start_time': start_time_obj.strftime('%H:%M:%S'),
                'end_time': end_time_calc.time().strftime('%H:%M:%S'),
                'is_break': is_break,
                'break_name': break_name,
                'duration': duration
            })
            
            current_time = end_time_calc
        
        return periods


class TimetableConfigHistory(TenantAwareModel):
    """
    Track changes to timetable settings for audit purposes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timetable_settings = models.ForeignKey(
        TimetableSettings,
        on_delete=models.CASCADE,
        related_name='change_history'
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changes = models.JSONField(
        help_text="Dictionary of changes made (field_name: {'old': value, 'new': value})"
    )

    class Meta:
        ordering = ['-changed_at']
        verbose_name_plural = "Timetable Settings History"

    def __str__(self):
        return f"Change on {self.changed_at.strftime('%Y-%m-%d %H:%M')} by {self.changed_by}"


# ============================================================
# GRIEVANCE MODEL (from feature/parent-grievance branch)
# ============================================================

class Grievance(TenantAwareModel):
    """
    Student/Parent grievance tracking system.
    """
    class PriorityChoices(models.TextChoices):
        LOW = 'Low', 'Low'
        MEDIUM = 'Medium', 'Medium'
        HIGH = 'High', 'High'
        URGENT = 'Urgent', 'Urgent'

    class StatusChoices(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        IN_PROGRESS = 'In-Progress', 'In-Progress'
        RESOLVED = 'Resolved', 'Resolved'
        CLOSED = 'Closed', 'Closed'
        REJECTED = 'Rejected', 'Rejected'

    class SourceChoices(models.TextChoices):
        STUDENT = 'Student', 'Student'
        PARENT = 'Parent', 'Parent'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='submitted_grievances'
    )
    source_type = models.CharField(max_length=20, choices=SourceChoices.choices)
    
    student = models.ForeignKey(
        'profiles.StudentProfile', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='grievances'
    )
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=100, blank=True, null=True)
    priority = models.CharField(max_length=20, choices=PriorityChoices.choices, default=PriorityChoices.MEDIUM)
    
    status = models.CharField(max_length=20, choices=StatusChoices.choices, default=StatusChoices.PENDING)
    
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='assigned_grievances'
    )
    admin_remarks = models.TextField(blank=True, null=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['submitted_by', 'status']),
        ]

    def __str__(self):
        return f"{self.title[:50]} - {self.status} ({self.submitted_by.email})"


# ============================================================
# CIRCULAR MODEL (from main branch)
# ============================================================

class Circular(TenantAwareModel):
    """
    A school-wide circular posted by the admin.
    Students, teachers, and parents can read it based on target_audience.
    """

    class AudienceChoice(models.TextChoices):
        ALL      = 'all',      'All'
        STUDENTS = 'students', 'Students'
        TEACHERS = 'teachers', 'Teachers'
        PARENTS  = 'parents',  'Parents'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    title = models.CharField(max_length=255)
    content = models.TextField()

    target_audience = models.CharField(
        max_length=20,
        choices=AudienceChoice.choices,
        default=AudienceChoice.ALL,
        db_index=True,
    )

    # Optional: restrict to specific class levels (empty = all classes)
    target_class_levels = models.ManyToManyField(
        'academics.ClassLevel',
        blank=True,
        related_name='circulars',
        help_text="Leave empty to target every class in the school.",
    )

    # Optional file attachment stored in R2 (same pattern as profile pictures)
    attachment_key = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="R2 object key for the attached file."
    )
    attachment_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Original filename shown to recipients."
    )

    is_published = models.BooleanField(
        default=True,
        help_text="Unpublish to hide from recipients without deleting.",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='circulars_created',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_target_audience_display()}] {self.title} ({self.school.name})"