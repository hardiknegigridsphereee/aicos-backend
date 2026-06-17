from rest_framework import serializers
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from profiles.models import StudentProfile, TeacherProfile
from academics.models import TeacherAssignment

# --- EXISTING ATTENDANCE SERIALIZERS ---
class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_enrollment_no = serializers.CharField(source='student.enrollment_number', read_only=True)

    class Meta:
        model = Attendance
        fields = '__all__'
        read_only_fields = ('school', 'id')

class AttendanceRecordItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=Attendance.StatusChoices.choices)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)

class BulkAttendanceSerializer(serializers.Serializer):
    date = serializers.DateField()
    academic_year_id = serializers.UUIDField()
    class_level_id = serializers.UUIDField()
    section_id = serializers.UUIDField()
    records = AttendanceRecordItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        request = self.context.get('request')
        school = request.user.school

        student_ids = [record['student_id'] for record in attrs['records']]
        valid_students_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()

        if valid_students_count != len(student_ids):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")
        return attrs

# --- EXAM & GRADING SERIALIZERS ---

class ExamSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = Exam
        fields = '__all__'
        read_only_fields = ('school', 'id')

class StudentGradeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    exam_name = serializers.CharField(source='exam.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = StudentGrade
        fields = '__all__'
        read_only_fields = ('school', 'id')

# --- BULK GRADING LOGIC ---

class GradeRecordItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    marks_obtained = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_marks = serializers.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)

class BulkGradeSubmitSerializer(serializers.Serializer):
    """
    Validates the payload for submitting an entire column of grades.
    Enforces strict Teacher-Subject-Section RBAC logic.
    """
    exam_id = serializers.UUIDField()
    subject_id = serializers.UUIDField()
    section_id = serializers.UUIDField()
    records = GradeRecordItemSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        request = self.context.get('request')
        user = request.user
        school = user.school

        exam = Exam.objects.filter(id=attrs['exam_id'], school=school).first()
        if not exam:
            raise serializers.ValidationError({"exam_id": "Invalid Exam or does not belong to your school."})

        if not (user.is_superuser or user.is_staff):
            teacher_profile = TeacherProfile.objects.filter(user=user).first()
            if not teacher_profile:
                raise serializers.ValidationError("You must be a registered teacher to submit grades.")

            is_assigned = TeacherAssignment.objects.filter(
                school=school,
                teacher=teacher_profile,
                subject_id=attrs['subject_id'],
                section_id=attrs['section_id'],
                academic_year=exam.academic_year
            ).exists()

            if not is_assigned:
                raise serializers.ValidationError(
                    "Security Exception: You are not assigned to teach this subject to this section. Grading access denied."
                )

        student_ids = [record['student_id'] for record in attrs['records']]
        valid_students_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()
        if valid_students_count != len(student_ids):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")

        return attrs


# --- ASSIGNMENTS & SUBMISSIONS ---

class AssignmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.user.first_name', read_only=True)

    class Meta:
        model = Assignment
        fields = '__all__'
        read_only_fields = ('school', 'id', 'created_at')

class StudentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)

    class Meta:
        model = StudentSubmission
        fields = '__all__'
        read_only_fields = ('school', 'id', 'submitted_at')


class StudentSubmissionCreateSerializer(serializers.ModelSerializer):
    """
    Used only for the student-facing submit action.
    Deliberately excludes `grade` and `status` from writable fields —
    a student submitting their own work cannot also grade it in the
    same request. Grading is a separate, teacher-only action.
    """
    class Meta:
        model = StudentSubmission
        fields = ['id', 'assignment', 'file', 'submitted_at', 'status']
        read_only_fields = ['id', 'submitted_at', 'status']


class AssignmentWithStatusSerializer(serializers.ModelSerializer):
    """
    Read-only merged view: one assignment row plus this specific student's
    submission status for it. Used by the new /assignments/for-student/ endpoint
    so the frontend never has to manually join two separate lists.
    """
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.user.first_name', read_only=True)

    submission_status = serializers.SerializerMethodField()
    submission_id = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    file = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'subject', 'subject_name',
            'section', 'section_name', 'teacher', 'teacher_name', 'due_date',
            'created_at', 'submission_status', 'submission_id', 'grade',
            'submitted_at', 'file',
        ]

    def _get_submission(self, obj):
        # The view attaches `student_id` onto the serializer context so this
        # works the same whether the caller is the student themselves or a parent.
        student_id = self.context.get('student_id')
        if not student_id:
            return None
        if not hasattr(obj, '_submission_cache'):
            obj._submission_cache = StudentSubmission.objects.filter(
                assignment=obj, student_id=student_id
            ).first()
        return obj._submission_cache

    def get_submission_status(self, obj):
        submission = self._get_submission(obj)
        return submission.status if submission else "Pending"

    def get_submission_id(self, obj):
        submission = self._get_submission(obj)
        return str(submission.id) if submission else None

    def get_grade(self, obj):
        submission = self._get_submission(obj)
        return str(submission.grade) if submission and submission.grade is not None else None

    def get_submitted_at(self, obj):
        submission = self._get_submission(obj)
        return submission.submitted_at if submission else None

    def get_file(self, obj):
        submission = self._get_submission(obj)
        return submission.file.url if submission and submission.file else None