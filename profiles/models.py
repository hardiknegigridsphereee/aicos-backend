# profiles/models.py
import uuid
from django.db import models
from django.conf import settings
from tenants.models import TenantAwareModel

class BaseProfile(TenantAwareModel):
    """
    Abstract base class containing common fields for all human entities.
    Inherits from TenantAwareModel to ensure tenant isolation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/pictures/', blank=True, null=True)

    class Meta:
        abstract = True


class StudentProfile(BaseProfile):
    """Profile specifically for Students."""
    enrollment_number = models.CharField(max_length=50)
    blood_group = models.CharField(max_length=10, blank=True, null=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['school', 'enrollment_number'], name='unique_school_enrollment')
        ]

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} - {self.enrollment_number}"
    
    def get_last_location(self):
        """Get the student's last known location from their device."""
        if hasattr(self, 'device') and self.device.last_latitude and self.device.last_longitude:
            return {
                'latitude': float(self.device.last_latitude),
                'longitude': float(self.device.last_longitude),
                'timestamp': self.device.last_location_update,
                'device': self.device.device_name
            }
        return None
    
    def get_location_history(self, days=7):
        """Get location history for the past N days."""
        from django.utils import timezone
        from datetime import timedelta
        
        cutoff = timezone.now() - timedelta(days=days)
        return self.location_history.filter(location_time__gte=cutoff).order_by('-location_time')


class TeacherProfile(BaseProfile):
    """Profile specifically for Teachers/Educators."""
    employee_id = models.CharField(max_length=50)
    qualification = models.CharField(max_length=255, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['school', 'employee_id'], name='unique_school_employee_id')
        ]

    def __str__(self):
        return f"Prof. {self.user.last_name} ({self.employee_id})"


class ParentProfile(BaseProfile):
    """Profile specifically for Parents/Guardians."""
    occupation = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_number = models.CharField(max_length=20, blank=True, null=True)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f"{self.user.first_name} {self.user.last_name} (Parent)"


class ParentStudentMapping(TenantAwareModel):
    """
    Maps a parent to a student. This handles complex family structures 
    (e.g., siblings, divorced parents, step-parents) securely.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey(ParentProfile, on_delete=models.CASCADE, related_name='student_mappings')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='parent_mappings')
    relationship = models.CharField(max_length=50)
    is_primary_contact = models.BooleanField(default=True)
    can_view_academics = models.BooleanField(default=True)
    can_pay_fees = models.BooleanField(default=True)

    class Meta:
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['parent', 'student'], name='unique_parent_student_mapping')
        ]

    def __str__(self):
        return f"{self.parent.user.first_name} -> {self.student.user.first_name} ({self.relationship})"


class StudentDevice(TenantAwareModel):
    """
    Tracks student devices for location tracking.
    """
    class DeviceType(models.TextChoices):
        PHONE = 'phone', 'Phone'
        TABLET = 'tablet', 'Tablet'
        SMARTWATCH = 'smartwatch', 'Smartwatch'
        OTHER = 'other', 'Other'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.OneToOneField(
        StudentProfile, 
        on_delete=models.CASCADE,
        related_name='device'
    )
    imei_number = models.CharField(
        max_length=20, 
        unique=True,
        help_text="Unique IMEI number of the device"
    )
    device_type = models.CharField(
        max_length=20, 
        choices=DeviceType.choices,
        default=DeviceType.PHONE
    )
    device_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_location_update = models.DateTimeField(null=True, blank=True)
    last_latitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True
    )
    last_longitude = models.DecimalField(
        max_digits=10, 
        decimal_places=7,
        null=True, 
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Student Device'
        verbose_name_plural = 'Student Devices'
        indexes = [
            models.Index(fields=['imei_number']),
            models.Index(fields=['student', 'is_active']),
        ]

    def __str__(self):
        return f"{self.student.user.first_name} {self.student.user.last_name} - {self.imei_number} ({self.get_device_type_display()})"
    
    def update_location(self, latitude, longitude, location_time=None, **kwargs):
        """Update the device's last known location."""
        from django.utils import timezone
        
        if location_time is None:
            location_time = timezone.now()
        
        self.last_latitude = latitude
        self.last_longitude = longitude
        self.last_location_update = location_time
        self.save(update_fields=['last_latitude', 'last_longitude', 'last_location_update', 'updated_at'])
        
        history = StudentLocationHistory(
            school=self.school,
            device=self,
            student=self.student,
            latitude=latitude,
            longitude=longitude,
            location_time=location_time,
            accuracy=kwargs.get('accuracy'),
            altitude=kwargs.get('altitude'),
            speed=kwargs.get('speed'),
            heading=kwargs.get('heading'),
        )
        history.save()
        return history


class StudentLocationHistory(TenantAwareModel):
    """
    Stores historical location data for students.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        StudentDevice, 
        on_delete=models.CASCADE,
        related_name='location_history'
    )
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE,
        related_name='location_history'
    )
    latitude = models.DecimalField(max_digits=10, decimal_places=7)
    longitude = models.DecimalField(max_digits=10, decimal_places=7)
    accuracy = models.FloatField(null=True, blank=True, help_text="Accuracy in meters")
    altitude = models.FloatField(null=True, blank=True, help_text="Altitude in meters")
    speed = models.FloatField(null=True, blank=True, help_text="Speed in m/s")
    heading = models.FloatField(null=True, blank=True, help_text="Heading in degrees")
    location_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-location_time']
        verbose_name = 'Student Location History'
        verbose_name_plural = 'Student Location Histories'
        indexes = [
            models.Index(fields=['student', 'location_time']),
            models.Index(fields=['device', 'location_time']),
        ]

    def __str__(self):
        return f"{self.student.user.first_name} - {self.location_time.strftime('%Y-%m-%d %H:%M')}"