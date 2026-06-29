from rest_framework import serializers
from profiles.models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from academics.models import TeacherAssignment


class SchoolAdminStudentListSerializer(serializers.ModelSerializer):
    """
    Lightweight student list serializer for school admin.
    """
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    current_class = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'enrollment_number',
            'blood_group',
            'phone_number',
            'date_of_birth',
            'is_archived',
            'is_active',
            'date_joined',
            'current_class',
        ]

    def get_current_class(self, obj):
        enrollment = getattr(obj, '_current_enrollment', None)
        if not enrollment:
            return None
        return {
            'enrollment_id': str(enrollment.id),
            'class_level': enrollment.class_level.name,
            'section': enrollment.section.name,
            'academic_year': enrollment.academic_year.name,
            'roll_number': enrollment.roll_number,
        }


class SchoolAdminTeacherListSerializer(serializers.ModelSerializer):
    """
    Teacher list serializer for school admin.
    """
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    assignment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = TeacherProfile
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'employee_id',
            'qualification',
            'joining_date',
            'phone_number',
            'date_of_birth',
            'is_active',
            'date_joined',
            'assignment_count',
        ]


class SchoolAdminTeacherAssignmentSerializer(serializers.ModelSerializer):
    """
    Shows which teacher is assigned to which class/section/subject.
    """
    teacher_id = serializers.UUIDField(source='teacher.id', read_only=True)
    teacher_first_name = serializers.CharField(source='teacher.user.first_name', read_only=True)
    teacher_last_name = serializers.CharField(source='teacher.user.last_name', read_only=True)
    teacher_email = serializers.EmailField(source='teacher.user.email', read_only=True)
    teacher_employee_id = serializers.CharField(source='teacher.employee_id', read_only=True)

    class_level_id = serializers.UUIDField(source='class_level.id', read_only=True)
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)

    section_id = serializers.UUIDField(source='section.id', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)

    subject_id = serializers.UUIDField(source='subject.id', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)

    academic_year_id = serializers.UUIDField(source='academic_year.id', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)

    class Meta:
        model = TeacherAssignment
        fields = [
            'id',
            'teacher_id',
            'teacher_first_name',
            'teacher_last_name',
            'teacher_email',
            'teacher_employee_id',
            'class_level_id',
            'class_level_name',
            'section_id',
            'section_name',
            'subject_id',
            'subject_name',
            'subject_code',
            'academic_year_id',
            'academic_year_name',
            'is_class_teacher',
        ]


class SchoolAdminParentStudentMappingSerializer(serializers.ModelSerializer):
    """
    Read-only parent-student mapping view for school admin.
    """
    parent_id = serializers.UUIDField(source='parent.id', read_only=True)
    parent_first_name = serializers.CharField(source='parent.user.first_name', read_only=True)
    parent_last_name = serializers.CharField(source='parent.user.last_name', read_only=True)
    parent_email = serializers.EmailField(source='parent.user.email', read_only=True)
    parent_phone = serializers.CharField(source='parent.phone_number', read_only=True)

    student_id = serializers.UUIDField(source='student.id', read_only=True)
    student_first_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_last_name = serializers.CharField(source='student.user.last_name', read_only=True)
    student_email = serializers.EmailField(source='student.user.email', read_only=True)
    student_enrollment_number = serializers.CharField(source='student.enrollment_number', read_only=True)

    class Meta:
        model = ParentStudentMapping
        fields = [
            'id',
            'parent_id',
            'parent_first_name',
            'parent_last_name',
            'parent_email',
            'parent_phone',
            'student_id',
            'student_first_name',
            'student_last_name',
            'student_email',
            'student_enrollment_number',
            'relationship',
            'is_primary_contact',
            'can_view_academics',
            'can_pay_fees',
        ]


class SchoolAdminParentListSerializer(serializers.ModelSerializer):
    """
    Parent list serializer for school admin.
    Includes the parent's own details plus a summary of all linked children.
    Children are annotated by the view to avoid N+1.
    """
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    date_joined = serializers.DateTimeField(source='user.date_joined', read_only=True)
    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    children = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = ParentProfile
        fields = [
            'id',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'emergency_contact_number',
            'occupation',
            'address',
            'date_of_birth',
            'is_active',
            'date_joined',
            'children_count',
            'children',
        ]

    def get_children(self, obj):
        # Annotated by view as _children_mappings to avoid N+1
        mappings = getattr(obj, '_children_mappings', [])
        result = []
        for mapping in mappings:
            student = mapping.student
            result.append({
                'mapping_id': str(mapping.id),
                'student_id': str(student.id),
                'first_name': student.user.first_name,
                'last_name': student.user.last_name,
                'email': student.user.email,
                'enrollment_number': student.enrollment_number,
                'relationship': mapping.relationship,
                'is_primary_contact': mapping.is_primary_contact,
                'can_view_academics': mapping.can_view_academics,
                'can_pay_fees': mapping.can_pay_fees,
            })
        return result

    def get_children_count(self, obj):
        mappings = getattr(obj, '_children_mappings', [])
        return len(mappings)