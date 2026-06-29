import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from tenants.models import TenantAwareModel


class LeaveRequest(TenantAwareModel):
    """
    A single model that handles leave applications for BOTH students and
    teachers, since the approval workflow is structurally identical:

        Student  -> applies -> reviewed by a Teacher
        Teacher  -> applies -> reviewed by a School Admin (staff/superuser)

    Exactly one of `student` / `teacher` must be set, matching
    `applicant_role`. This is enforced in `clean()` and in the serializer.
    """

    class ApplicantRole(models.TextChoices):
        STUDENT = 'Student', 'Student'
        TEACHER = 'Teacher', 'Teacher'

    class LeaveType(models.TextChoices):
        SICK = 'Sick', 'Sick'
        CASUAL = 'Casual', 'Casual'
        EMERGENCY = 'Emergency', 'Emergency'
        OTHER = 'Other', 'Other'

    class StatusChoices(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        APPROVED = 'Approved', 'Approved'
        REJECTED = 'Rejected', 'Rejected'
        CANCELLED = 'Cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    applicant_role = models.CharField(max_length=10, choices=ApplicantRole.choices)

    # Exactly one of these two will be populated, based on applicant_role.
    student = models.ForeignKey(
        'profiles.StudentProfile',
        on_delete=models.CASCADE,
        related_name='leave_requests',
        null=True,
        blank=True,
    )
    teacher = models.ForeignKey(
        'profiles.TeacherProfile',
        on_delete=models.CASCADE,
        related_name='leave_requests',
        null=True,
        blank=True,
    )

    leave_type = models.CharField(max_length=20, choices=LeaveType.choices, default=LeaveType.CASUAL)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()

    # Optional supporting document (e.g. medical certificate), reuses the
    # same upload-to-R2 flow as other FileFields in this project.
    attachment = models.FileField(upload_to='leave_attachments/', blank=True, null=True, max_length=500)

    status = models.CharField(max_length=10, choices=StatusChoices.choices, default=StatusChoices.PENDING)

    applied_at = models.DateTimeField(auto_now_add=True)

    # Whoever actioned the request: a Teacher (User) for student leaves,
    # or a School Admin / staff (User) for teacher leaves.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leave_requests_reviewed',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_remarks = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-applied_at']
        indexes = [
            models.Index(fields=['school', 'applicant_role', 'status']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['teacher', 'status']),
        ]

    def clean(self):
        if self.applicant_role == self.ApplicantRole.STUDENT:
            if not self.student_id or self.teacher_id:
                raise ValidationError("A student leave request must set `student` and leave `teacher` empty.")
        elif self.applicant_role == self.ApplicantRole.TEACHER:
            if not self.teacher_id or self.student_id:
                raise ValidationError("A teacher leave request must set `teacher` and leave `student` empty.")

        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date cannot be before the start date."})

    @property
    def total_days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    @property
    def applicant_name(self):
        if self.applicant_role == self.ApplicantRole.STUDENT and self.student_id:
            return f"{self.student.user.first_name} {self.student.user.last_name}"
        if self.applicant_role == self.ApplicantRole.TEACHER and self.teacher_id:
            return f"{self.teacher.user.first_name} {self.teacher.user.last_name}"
        return None

    def __str__(self):
        return f"{self.applicant_role} leave ({self.start_date} - {self.end_date}) [{self.status}]"
