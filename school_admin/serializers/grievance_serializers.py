# school_admin/serializers/grievance_serializers.py
from rest_framework import serializers
from school_admin.models import Grievance


class GrievanceSerializer(serializers.ModelSerializer):
    """
    Full Grievance serializer for detail views.
    All computed fields are read-only; writable FK fields (student, assigned_to)
    accept a UUID on write and return nested data on read.
    """
    submitted_by_name  = serializers.SerializerMethodField()
    submitted_by_email = serializers.EmailField(source='submitted_by.email', read_only=True)
    submitted_by_role  = serializers.SerializerMethodField()
    student_name       = serializers.SerializerMethodField()
    student_enrollment = serializers.SerializerMethodField()
    assigned_to_name   = serializers.SerializerMethodField()
    assigned_to_email  = serializers.EmailField(source='assigned_to.email', read_only=True)

    class Meta:
        model  = Grievance
        fields = [
            'id',
            'title',
            'description',
            'category',
            'priority',
            'status',
            'source_type',
            # submitted_by
            'submitted_by',
            'submitted_by_name',
            'submitted_by_email',
            'submitted_by_role',
            # student
            'student',
            'student_name',
            'student_enrollment',
            # assignment / resolution
            'assigned_to',
            'assigned_to_name',
            'assigned_to_email',
            'admin_remarks',
            # timestamps
            'created_at',
            'updated_at',
            'resolved_at',
        ]
        read_only_fields = [
            'id',
            'submitted_by',
            'source_type',
            'created_at',
            'updated_at',
            'resolved_at',
            # computed
            'submitted_by_name',
            'submitted_by_email',
            'submitted_by_role',
            'student_name',
            'student_enrollment',
            'assigned_to_name',
            'assigned_to_email',
        ]

    def get_submitted_by_name(self, obj):
        u = obj.submitted_by
        return f"{u.first_name} {u.last_name}".strip() or u.email

    def get_submitted_by_role(self, obj):
        u = obj.submitted_by
        if hasattr(u, 'studentprofile'):
            return 'Student'
        if hasattr(u, 'parentprofile'):
            return 'Parent'
        return 'Staff'

    def get_student_name(self, obj):
        if obj.student:
            u = obj.student.user
            return f"{u.first_name} {u.last_name}".strip() or u.email
        return None

    def get_student_enrollment(self, obj):
        return obj.student.enrollment_number if obj.student else None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            u = obj.assigned_to
            return f"{u.first_name} {u.last_name}".strip() or u.email
        return None


class GrievanceCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new grievance (students & parents only).
    submitted_by and school are injected by the view – never accepted from input.
    """
    # student is optional at the serializer level; business logic enforces
    # it for parents inside validate().
    student = serializers.PrimaryKeyRelatedField(
        queryset=__import__(
            'profiles.models', fromlist=['StudentProfile']
        ).StudentProfile.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model  = Grievance
        fields = [
            'title',
            'description',
            'category',
            'priority',
            'student',
        ]

    def validate(self, attrs):
        request = self.context['request']
        user    = request.user

        # Verify student belongs to the same school when supplied
        student = attrs.get('student')
        if student and student.school != user.school:
            raise serializers.ValidationError(
                {'student': 'This student does not belong to your school.'}
            )

        # Parents must always supply a student
        if hasattr(user, 'parentprofile') and not student:
            raise serializers.ValidationError(
                {'student': 'Parent must specify a student when submitting a grievance.'}
            )

        # Only students and parents may submit
        if not hasattr(user, 'studentprofile') and not hasattr(user, 'parentprofile'):
            raise serializers.ValidationError(
                {'detail': 'Only students and parents can submit grievances.'}
            )

        return attrs

    def create(self, validated_data):
        """
        The view calls serializer.save(submitted_by=..., school=...) which
        passes those kwargs directly into this method via **validated_data
        after DRF merges them.  We just need to determine source_type here.
        """
        request = self.context['request']
        user    = request.user

        if hasattr(user, 'studentprofile'):
            validated_data['source_type'] = Grievance.SourceChoices.STUDENT
            # Auto-assign student to the submitter if not explicitly provided
            if not validated_data.get('student'):
                validated_data['student'] = user.studentprofile
        else:
            validated_data['source_type'] = Grievance.SourceChoices.PARENT

        return Grievance.objects.create(**validated_data)


class GrievanceUpdateSerializer(serializers.ModelSerializer):
    """
    Admin-only: update status, priority, assignee, and remarks.
    resolved_at is set automatically when status becomes Resolved.
    """
    class Meta:
        model  = Grievance
        fields = [
            'status',
            'priority',
            'assigned_to',
            'admin_remarks',
        ]

    def update(self, instance, validated_data):
        from django.utils import timezone

        new_status = validated_data.get('status', instance.status)

        # Auto-stamp resolved_at when first moving to Resolved
        if (
            new_status == Grievance.StatusChoices.RESOLVED
            and instance.status != Grievance.StatusChoices.RESOLVED
        ):
            validated_data['resolved_at'] = timezone.now()

        return super().update(instance, validated_data)


class GrievanceAdminListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the admin list view.
    """
    submitted_by_name = serializers.SerializerMethodField()
    submitted_by_role = serializers.SerializerMethodField()
    student_name      = serializers.SerializerMethodField()
    assigned_to_name  = serializers.SerializerMethodField()

    class Meta:
        model  = Grievance
        fields = [
            'id',
            'title',
            'category',
            'priority',
            'status',
            'source_type',
            'submitted_by_name',
            'submitted_by_role',
            'student_name',
            'assigned_to_name',
            'created_at',
            'updated_at',
        ]

    def get_submitted_by_name(self, obj):
        u = obj.submitted_by
        return f"{u.first_name} {u.last_name}".strip() or u.email

    def get_submitted_by_role(self, obj):
        u = obj.submitted_by
        if hasattr(u, 'studentprofile'):
            return 'Student'
        if hasattr(u, 'parentprofile'):
            return 'Parent'
        return 'Staff'

    def get_student_name(self, obj):
        if obj.student:
            u = obj.student.user
            return f"{u.first_name} {u.last_name}".strip() or u.email
        return None

    def get_assigned_to_name(self, obj):
        if obj.assigned_to:
            u = obj.assigned_to
            return f"{u.first_name} {u.last_name}".strip() or u.email
        return None


class GrievanceStatsSerializer(serializers.Serializer):
    """
    Read-only statistics payload for the grievance dashboard.
    """
    total           = serializers.IntegerField()
    pending         = serializers.IntegerField()
    in_progress     = serializers.IntegerField()
    resolved        = serializers.IntegerField()
    closed          = serializers.IntegerField()
    rejected        = serializers.IntegerField()
    resolution_rate = serializers.FloatField()