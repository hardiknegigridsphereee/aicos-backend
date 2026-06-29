import uuid
from django.db import models
from django.core.exceptions import ValidationError
from tenants.models import TenantAwareModel

class Attendance(TenantAwareModel):
    """Tracks daily attendance for students."""
    class StatusChoices(models.TextChoices):
        PRESENT = 'Present', 'Present'
        ABSENT = 'Absent', 'Absent'
        LATE = 'Late', 'Late'
        HALF_DAY = 'Half-Day', 'Half-Day'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='attendance_records')
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE)
    class_level = models.ForeignKey('academics.ClassLevel', on_delete=models.CASCADE)
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE)
    
    date = models.DateField()
    status = models.CharField(max_length=10, choices=StatusChoices.choices, default=StatusChoices.PRESENT)
    remarks = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['-date', 'student__user__first_name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'student', 'date'], name='unique_student_attendance_per_day')
        ]

    def __str__(self):
        return f"{self.student.user.first_name} - {self.date} ({self.status})"


class Exam(TenantAwareModel):
    """Represents a specific testing event in the school year."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE, related_name='exams')
    
    start_date = models.DateField()
    end_date = models.DateField()
    is_published = models.BooleanField(default=False, help_text="Can parents/students see these results?")

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name', 'academic_year'], name='unique_exam_per_year')
        ]

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError("Exam end date cannot be before the start date.")

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class StudentGrade(TenantAwareModel):
    """Records a student's performance in a specific subject for a specific exam."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='grades')
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='grades')
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE, related_name='grades')
    
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    remarks = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ['student__user__first_name', 'subject__name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'exam', 'student', 'subject'], 
                name='unique_student_subject_grade_per_exam'
            )
        ]

    def clean(self):
        if self.marks_obtained is not None and self.max_marks is not None:
            if self.marks_obtained > self.max_marks:
                raise ValidationError({"marks_obtained": "Marks obtained cannot exceed maximum marks."})
            if self.marks_obtained < 0:
                raise ValidationError({"marks_obtained": "Marks obtained cannot be negative."})

    def __str__(self):
        return f"{self.student.user.first_name} | {self.exam.name} | {self.subject.name}: {self.marks_obtained}/{self.max_marks}"


class Assignment(TenantAwareModel):
    """Represents a task assigned by a teacher to a section."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    section = models.ForeignKey('academics.Section', on_delete=models.CASCADE)
    teacher = models.ForeignKey('profiles.TeacherProfile', on_delete=models.CASCADE)
    due_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-due_date']


class StudentSubmission(TenantAwareModel):
    """Tracks a student's submission for a specific assignment."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='submissions')
    file = models.FileField(upload_to='submissions/', blank=True, null=True, max_length=500)  # ← FIXED: max_length=500
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, default='Submitted')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['school', 'assignment', 'student'], name='unique_student_submission')
        ]

    def __str__(self):
        return f"{self.student.user.first_name} - {self.assignment.title}"


class PendingSubmission(TenantAwareModel):
    """Tracks pending file uploads before submission is finalized"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE)
    assignment = models.ForeignKey('operations.Assignment', on_delete=models.CASCADE)
    file_path = models.CharField(max_length=500)  # Already fixed
    file_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, default='application/pdf')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'assignment', 'is_completed']),
        ]
    
    def __str__(self):
        return f"Pending: {self.student.user.first_name} - {self.assignment.title}"