# school_admin/serializers/circular_serializers.py

from rest_framework import serializers
from school_admin.models import Circular
from academics.models import ClassLevel


class CircularSerializer(serializers.ModelSerializer):
    """
    Full serializer used for:
      - Admin   → create / retrieve / update / delete
      - Others  → retrieve / list  (read-only fields enforced by ViewSet permissions)
    """

    # Read-only computed fields
    created_by_name = serializers.SerializerMethodField()
    target_audience_display = serializers.CharField(
        source='get_target_audience_display', read_only=True
    )
    target_class_level_names = serializers.SerializerMethodField()

    # Writable: accept a list of ClassLevel UUIDs on POST/PATCH/PUT
    target_class_levels = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=ClassLevel.objects.all(),
        required=False,
    )

    class Meta:
        model  = Circular
        fields = [
            'id',
            'title',
            'content',
            'target_audience',
            'target_audience_display',
            'target_class_levels',
            'target_class_level_names',
            'attachment_key',
            'attachment_name',
            'is_published',
            'created_by',
            'created_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    # ------------------------------------------------------------------
    # Custom field methods
    # ------------------------------------------------------------------

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return None

    def get_target_class_level_names(self, obj):
        return list(obj.target_class_levels.values_list('name', flat=True))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_target_class_levels(self, value):
        """
        Make sure every supplied ClassLevel belongs to the requesting admin's school.
        Falls back gracefully when there is no request context (e.g. shell).
        """
        request = self.context.get('request')
        if request and value:
            school = request.user.school
            for cl in value:
                if cl.school != school:
                    raise serializers.ValidationError(
                        f"ClassLevel '{cl.name}' does not belong to your school."
                    )
        return value


class CircularListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views – avoids sending full content body.
    """
    created_by_name = serializers.SerializerMethodField()
    target_audience_display = serializers.CharField(
        source='get_target_audience_display', read_only=True
    )
    target_class_level_names = serializers.SerializerMethodField()

    class Meta:
        model  = Circular
        fields = [
            'id',
            'title',
            'target_audience',
            'target_audience_display',
            'target_class_level_names',
            'attachment_name',
            'is_published',
            'created_by_name',
            'created_at',
        ]

    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return None

    def get_target_class_level_names(self, obj):
        return list(obj.target_class_levels.values_list('name', flat=True))
