# timetable/serializers.py
from rest_framework import serializers
from .models import TimeSlot, TimetableEntry, TimetableTemplate
from academics.models import ClassLevel, Section, Subject
from profiles.models import TeacherProfile


class TimeSlotSerializer(serializers.ModelSerializer):
    day_label = serializers.SerializerMethodField()
    
    class Meta:
        model = TimeSlot
        fields = [
            'id', 'day', 'day_label', 'start_time', 'end_time',
            'period_number', 'is_break', 'break_name', 'academic_year'
        ]
        read_only_fields = ['id', 'school']

    def get_day_label(self, obj):
        return dict(TimeSlot.DAY_CHOICES).get(obj.day, obj.day)


class TimeSlotCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeSlot
        fields = ['day', 'start_time', 'end_time', 'period_number', 'is_break', 'break_name', 'academic_year']
        read_only_fields = ['id', 'school']


class TimetableEntrySerializer(serializers.ModelSerializer):
    # Nested fields for detail views
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)
    section_name = serializers.CharField(source='section.name', read_only=True)
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    subject_code = serializers.CharField(source='subject.code', read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_employee_id = serializers.CharField(source='teacher.employee_id', read_only=True)
    time_slot_detail = TimeSlotSerializer(source='time_slot', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    day = serializers.CharField(source='time_slot.day', read_only=True)
    period_number = serializers.IntegerField(source='time_slot.period_number', read_only=True)
    
    class Meta:
        model = TimetableEntry
        fields = [
            'id', 'class_level', 'class_level_name', 'section', 'section_name',
            'subject', 'subject_name', 'subject_code', 'teacher', 'teacher_name',
            'teacher_employee_id', 'time_slot', 'time_slot_detail', 'academic_year',
            'academic_year_name', 'day', 'period_number', 'room_number', 'notes',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_at', 'updated_at', 'created_by']

    def get_teacher_name(self, obj):
        if obj.teacher:
            return f"{obj.teacher.user.first_name} {obj.teacher.user.last_name}".strip()
        return None


class TimetableEntryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableEntry
        fields = [
            'class_level', 'section', 'subject', 'teacher',
            'time_slot', 'academic_year', 'room_number', 'notes'
        ]

    def validate(self, attrs):
        # Validate section belongs to class_level
        section = attrs.get('section')
        class_level = attrs.get('class_level')
        if section and class_level and section.class_level != class_level:
            raise serializers.ValidationError(
                {"section": "Section does not belong to the selected class level."}
            )
        return attrs


class TimetableEntryUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableEntry
        fields = [
            'class_level', 'section', 'subject', 'teacher',
            'time_slot', 'room_number', 'notes', 'is_active'
        ]

    def validate(self, attrs):
        # Validate section belongs to class_level
        section = attrs.get('section')
        class_level = attrs.get('class_level')
        if section and class_level and section.class_level != class_level:
            raise serializers.ValidationError(
                {"section": "Section does not belong to the selected class level."}
            )
        return attrs


class TimetableEntryBulkCreateSerializer(serializers.Serializer):
    """
    Serializer for bulk creating timetable entries.
    """
    entries = TimetableEntryCreateSerializer(many=True)
    academic_year_id = serializers.UUIDField()
    
    def validate(self, attrs):
        request = self.context.get('request')
        school = request.user.school
        
        # Validate all entries in the list
        for entry in attrs['entries']:
            # Validate each entry
            class_level = entry.get('class_level')
            section = entry.get('section')
            
            if section and class_level and section.class_level != class_level:
                raise serializers.ValidationError(
                    f"Section '{section.name}' does not belong to Class '{class_level.name}'."
                )
            
            # Check for duplicate entries (same section + time_slot)
            existing = TimetableEntry.objects.filter(
                school=school,
                section=entry.get('section'),
                time_slot=entry.get('time_slot'),
                academic_year_id=attrs['academic_year_id'],
                is_active=True
            ).exists()
            
            if existing:
                raise serializers.ValidationError(
                    f"Duplicate entry: Section {section.name} already has a class at this time."
                )
            
            # Check teacher availability
            teacher_exists = TimetableEntry.objects.filter(
                school=school,
                teacher=entry.get('teacher'),
                time_slot=entry.get('time_slot'),
                academic_year_id=attrs['academic_year_id'],
                is_active=True
            ).exists()
            
            if teacher_exists:
                raise serializers.ValidationError(
                    f"Teacher is already assigned to another class at this time."
                )
        
        return attrs


class TimetableTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimetableTemplate
        fields = [
            'id', 'name', 'description', 'academic_year', 'data',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'school', 'created_at', 'updated_at', 'created_by']


class TimetableSummarySerializer(serializers.Serializer):
    """
    Serializer for timetable summary - shows if settings exist and entries count.
    """
    settings_exist = serializers.BooleanField()
    total_entries = serializers.IntegerField()
    academic_year = serializers.CharField()
    working_days = serializers.ListField(child=serializers.CharField())
    periods_per_day = serializers.IntegerField()
    period_times = serializers.ListField()