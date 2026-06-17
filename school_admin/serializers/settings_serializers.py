from rest_framework import serializers
from school_admin.models import SchoolSettings
from tenants.models import School

class SchoolSettingsSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='school.name', required=False)

    class Meta:
        model = SchoolSettings
        fields = [
            'name', 'email', 'phone', 'country', 'address',
            'grading_scale', 'attendance_tracking_enabled', 'default_academic_year'
        ]

    def update(self, instance, validated_data):
        # Extract school name and update the related School model
        school_data = validated_data.pop('school', None)
        if school_data and 'name' in school_data:
            school = instance.school
            school.name = school_data['name']
            school.save(update_fields=['name'])
        return super().update(instance, validated_data)