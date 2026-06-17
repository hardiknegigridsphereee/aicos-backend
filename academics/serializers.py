from rest_framework import serializers
from .models import StudentEnrollment, TeacherAssignment, AcademicYear, ClassLevel, Section, Subject, SavedAIContent
from profiles.models import StudentProfile

class SavedAIContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedAIContent
        fields = '__all__'
        read_only_fields = ('school', 'id', 'teacher')

class AcademicYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcademicYear
        fields = '__all__'
        read_only_fields = ('school', 'id')

class ClassLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassLevel
        fields = '__all__'
        read_only_fields = ('school', 'id')

class SectionSerializer(serializers.ModelSerializer):
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)

    class Meta:
        model = Section
        fields = '__all__'
        read_only_fields = ('school', 'id')

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = '__all__'
        read_only_fields = ('school', 'id')

# --- EXISTING ENROLLMENT & ASSIGNMENT SERIALIZERS ---

class StudentEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_enrollment_no = serializers.CharField(source='student.enrollment_number', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)

    class Meta:
        model = StudentEnrollment
        fields = '__all__'
        read_only_fields = ('school', 'id', 'enrollment_date')

    def validate(self, attrs):
        """
        Custom validation to catch unique constraints elegantly before hitting the DB.
        """
        request = self.context.get('request')
        
        if request and request.method == 'POST':
            school = request.user.school
            student = attrs.get('student')
            academic_year = attrs.get('academic_year')

            if StudentEnrollment.objects.filter(school=school, student=student, academic_year=academic_year).exists():
                raise serializers.ValidationError(
                    {"non_field_errors": ["This student is already enrolled in this academic year. Please update the existing enrollment instead."]}
                )
                
        return attrs

class TeacherAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source='teacher.user.first_name', read_only=True)
    teacher_employee_id = serializers.CharField(source='teacher.employee_id', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)

    class Meta:
        model = TeacherAssignment
        fields = '__all__'
        read_only_fields = ('school', 'id')

class BulkPromotionSerializer(serializers.Serializer):
    """
    Validates the payload for bulk promoting students to a new academic year.
    """
    student_ids = serializers.ListField(
        child=serializers.UUIDField(), 
        allow_empty=False,
        help_text="List of StudentProfile UUIDs to promote."
    )
    target_academic_year_id = serializers.UUIDField()
    target_class_level_id = serializers.UUIDField()
    target_section_id = serializers.UUIDField()

    def validate(self, attrs):
        request = self.context.get('request')
        school = request.user.school

        student_count = StudentProfile.objects.filter(
            id__in=attrs['student_ids'], school=school
        ).count()
        if student_count != len(attrs['student_ids']):
            raise serializers.ValidationError("One or more students do not exist or belong to another school.")

        if not AcademicYear.objects.filter(id=attrs['target_academic_year_id'], school=school).exists():
            raise serializers.ValidationError({"target_academic_year_id": "Invalid academic year."})
        
        if not ClassLevel.objects.filter(id=attrs['target_class_level_id'], school=school).exists():
            raise serializers.ValidationError({"target_class_level_id": "Invalid class level."})

        if not Section.objects.filter(id=attrs['target_section_id'], school=school).exists():
            raise serializers.ValidationError({"target_section_id": "Invalid section."})

        return attrs