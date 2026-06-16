# school_admin/models.py
import uuid
from django.db import models
from django.conf import settings
from tenants.models import TenantAwareModel

class ActivityLog(TenantAwareModel):
    """Tracks administrative actions across the school."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action_type = models.CharField(max_length=50)  # e.g., "Student Registration"
    description = models.TextField()  # e.g., "Sarah Jenkins was added to Grade 10-B"
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


# ========== NEW MODEL ==========
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