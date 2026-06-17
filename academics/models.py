import uuid
from django.db import models
from django.core.exceptions import ValidationError
from tenants.models import TenantAwareModel

class AcademicYear(TenantAwareModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50) 
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False, help_text="Is this the current academic year?")

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='unique_school_academic_year')
        ]

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("End date must be after the start date.")

    def __str__(self):
        return f"{self.name} ({self.school.name})"

class ClassLevel(TenantAwareModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50)
    numeric_order = models.IntegerField(help_text="Used for sorting (e.g., Class 1 = 1, Class 10 = 10)")

    class Meta:
        ordering = ['numeric_order']
        constraints = [
            models.UniqueConstraint(fields=['school', 'name'], name='unique_school_class_name')
        ]

    def __str__(self):
        return f"{self.name} ({self.school.name})"

class Section(TenantAwareModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, related_name='sections')
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ['class_level__numeric_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'class_level', 'name'], name='unique_school_class_section')
        ]

    def __str__(self):
        return f"{self.class_level.name} - {self.name}"

class Subject(TenantAwareModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, null=True)
    class_levels = models.ManyToManyField(ClassLevel, related_name='subjects', blank=True)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'code'], name='unique_school_subject_code')
        ]

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name

# --- NEW MODEL FOR TASK 3.2 ---

class StudentEnrollment(TenantAwareModel):
    """
    The Engine of the ERP. Maps a student to a specific class/section for a specific year.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Using string reference 'profiles.StudentProfile' prevents circular import errors
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='enrollments')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='enrollments')
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, related_name='enrollments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='enrollments')
    
    roll_number = models.CharField(max_length=20, blank=True, null=True)
    enrollment_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-academic_year__start_date']
        constraints = [
            # CRITICAL: A student can only be enrolled ONCE per academic year in a school!
            models.UniqueConstraint(
                fields=['school', 'student', 'academic_year'], 
                name='unique_student_enrollment_per_year'
            )
        ]

    def __str__(self):
        return f"{self.student.user.first_name} -> {self.class_level.name} {self.section.name} ({self.academic_year.name})"

class TeacherAssignment(TenantAwareModel):
    """
    Maps a teacher to a specific subject, section, and academic year.
    Crucial for Phase 4 (Grades) to verify if a teacher is allowed to grade a section.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Using string reference 'profiles.TeacherProfile' prevents circular import errors
    teacher = models.ForeignKey('profiles.TeacherProfile', on_delete=models.CASCADE, related_name='assignments')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='teacher_assignments')
    class_level = models.ForeignKey(ClassLevel, on_delete=models.CASCADE, related_name='teacher_assignments')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='teacher_assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teacher_assignments')
    
    # Optional: Designate if they are the primary homeroom/class teacher
    is_class_teacher = models.BooleanField(default=False)

    class Meta:
        ordering = ['-academic_year__start_date', 'class_level__numeric_order']
        constraints = [
            # A teacher cannot be assigned to teach the SAME subject to the SAME section multiple times in one year
            models.UniqueConstraint(
                fields=['school', 'teacher', 'academic_year', 'section', 'subject'], 
                name='unique_teacher_subject_assignment'
            )
        ]

    def __str__(self):
        return f"{self.teacher.user.last_name} -> {self.subject.name} ({self.section.name})"

class SavedAIContent(TenantAwareModel):
    """
    Stores AI-generated content (Quiz, Lesson Plan, etc.) saved by teachers.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey('profiles.TeacherProfile', on_delete=models.CASCADE, related_name='saved_ai_contents')
    class_name = models.CharField(max_length=50, blank=True, null=True)
    subject = models.CharField(max_length=100, blank=True, null=True)
    content_type = models.CharField(max_length=50) # e.g., 'Quiz', 'Lesson Plan'
    data = models.JSONField() # Stores the actual generated content
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.content_type} by {self.teacher.user.last_name} ({self.updated_at.date()})"