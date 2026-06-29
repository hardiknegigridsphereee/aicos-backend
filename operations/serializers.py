from rest_framework import serializers
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from profiles.models import StudentProfile, TeacherProfile
from academics.models import TeacherAssignment

# ---------------------------------------------------------------------------
# ATTENDANCE
# ---------------------------------------------------------------------------

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
        student_ids = [r['student_id'] for r in attrs['records']]
        valid_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()
        if valid_count != len(student_ids):
            raise serializers.ValidationError(
                "One or more students do not exist or belong to another school."
            )
        return attrs


# ---------------------------------------------------------------------------
# EXAM & GRADES
# ---------------------------------------------------------------------------

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


class GradeRecordItemSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    marks_obtained = serializers.DecimalField(max_digits=5, decimal_places=2)
    max_marks = serializers.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)


class BulkGradeSubmitSerializer(serializers.Serializer):
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
            raise serializers.ValidationError({"exam_id": "Invalid exam or does not belong to your school."})

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
                    "You are not assigned to teach this subject to this section."
                )

        student_ids = [r['student_id'] for r in attrs['records']]
        valid_count = StudentProfile.objects.filter(id__in=student_ids, school=school).count()
        if valid_count != len(student_ids):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")

        return attrs


# ---------------------------------------------------------------------------
# ASSIGNMENTS
# ---------------------------------------------------------------------------

class AssignmentSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.user.first_name', read_only=True)

    class Meta:
        model = Assignment
        fields = '__all__'
        read_only_fields = ('school', 'id', 'created_at')


class AssignmentWithStatusSerializer(serializers.ModelSerializer):
    """
    Assignment row merged with the requesting student's submission status.
    Pass student_id in serializer context.
    """
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    teacher_name = serializers.CharField(source='teacher.user.first_name', read_only=True)

    submission_status = serializers.SerializerMethodField()
    submission_id = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    file_path = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id', 'title', 'description', 'subject', 'subject_name',
            'section', 'section_name', 'teacher', 'teacher_name', 'due_date',
            'created_at', 'submission_status', 'submission_id', 'grade',
            'submitted_at', 'file_path',
        ]

    def _get_submission(self, obj):
        student_id = self.context.get('student_id')
        if not student_id:
            return None
        if not hasattr(obj, '_submission_cache'):
            obj._submission_cache = StudentSubmission.objects.filter(
                assignment=obj, student_id=student_id
            ).first()
        return obj._submission_cache

    def get_submission_status(self, obj):
        s = self._get_submission(obj)
        return s.status if s else 'Pending'

    def get_submission_id(self, obj):
        s = self._get_submission(obj)
        return str(s.id) if s else None

    def get_grade(self, obj):
        s = self._get_submission(obj)
        return float(s.grade) if s and s.grade is not None else None

    def get_submitted_at(self, obj):
        s = self._get_submission(obj)
        return s.submitted_at if s else None

    def get_file_path(self, obj):
        s = self._get_submission(obj)
        if not s or not s.file:
            return None
        return str(s.file.name) if hasattr(s.file, 'name') else str(s.file)


# ---------------------------------------------------------------------------
# SUBMISSIONS
# ---------------------------------------------------------------------------

class StudentSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)

    class Meta:
        model = StudentSubmission
        fields = '__all__'
        read_only_fields = ('school', 'id', 'submitted_at')


class SubmissionWithViewUrlSerializer(serializers.ModelSerializer):
    """
    Submission row with all context a teacher or student needs,
    including an embedded 7-day view URL for the file.
    The view attaches _view_url to each instance before serialising.
    """
    student_name = serializers.SerializerMethodField()
    student_email = serializers.SerializerMethodField()
    enrollment_number = serializers.SerializerMethodField()
    assignment_title = serializers.SerializerMethodField()
    subject_name = serializers.SerializerMethodField()
    section_name = serializers.SerializerMethodField()
    due_date = serializers.SerializerMethodField()
    file_path = serializers.SerializerMethodField()
    view_url = serializers.SerializerMethodField()

    class Meta:
        model = StudentSubmission
        fields = [
            'id',
            'student_name', 'student_email', 'enrollment_number',
            'assignment_title', 'subject_name', 'section_name', 'due_date',
            'file_path', 'view_url',
            'submitted_at', 'status', 'grade',
        ]

    def get_student_name(self, obj):
        return f"{obj.student.user.first_name} {obj.student.user.last_name}"

    def get_student_email(self, obj):
        return obj.student.user.email

    def get_enrollment_number(self, obj):
        return obj.student.enrollment_number

    def get_assignment_title(self, obj):
        return obj.assignment.title

    def get_subject_name(self, obj):
        return obj.assignment.subject.name

    def get_section_name(self, obj):
        return obj.assignment.section.name

    def get_due_date(self, obj):
        return obj.assignment.due_date

    def get_file_path(self, obj):
        if not obj.file:
            return None
        return str(obj.file.name) if hasattr(obj.file, 'name') else str(obj.file)

    def get_view_url(self, obj):
        # Attached by the view to avoid generating URLs in the serializer
        return getattr(obj, '_view_url', None)