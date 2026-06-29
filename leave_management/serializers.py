from rest_framework import serializers

from .models import LeaveRequest


class LeaveRequestSerializer(serializers.ModelSerializer):
    applicant_name = serializers.CharField(read_only=True)
    total_days = serializers.IntegerField(read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'school', 'applicant_role', 'student', 'teacher',
            'applicant_name', 'leave_type', 'start_date', 'end_date',
            'total_days', 'reason', 'attachment', 'status',
            'applied_at', 'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'review_remarks',
        ]
        read_only_fields = [
            'id', 'school', 'applicant_role', 'student', 'teacher',
            'status', 'applied_at', 'reviewed_by', 'reviewed_at', 'review_remarks',
        ]

    def get_reviewed_by_name(self, obj):
        if not obj.reviewed_by_id:
            return None
        return f"{obj.reviewed_by.first_name} {obj.reviewed_by.last_name}".strip() or obj.reviewed_by.email


class LeaveRequestCreateSerializer(serializers.ModelSerializer):
    """
    Used for POST /leaves/. The view determines `applicant_role` and
    `student`/`teacher` from the requesting user's profile -- the client
    only ever supplies the leave details.
    """

    class Meta:
        model = LeaveRequest
        fields = ['id', 'leave_type', 'start_date', 'end_date', 'reason', 'attachment']
        read_only_fields = ['id']

    def validate(self, attrs):
        start = attrs.get('start_date')
        end = attrs.get('end_date')
        if start and end and start > end:
            raise serializers.ValidationError({"end_date": "End date cannot be before the start date."})
        return attrs


class LeaveReviewSerializer(serializers.Serializer):
    """Used for the approve/reject actions."""
    remarks = serializers.CharField(max_length=255, required=False, allow_blank=True)
