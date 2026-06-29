# school_admin/serializers/timetable_settings_serializers.py
from rest_framework import serializers
from school_admin.models import TimetableSettings, TimetableConfigHistory


class TimetableSettingsSerializer(serializers.ModelSerializer):
    """
    Serializer for timetable settings with computed fields.
    """
    total_periods_per_week = serializers.SerializerMethodField()
    period_times = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = TimetableSettings
        fields = [
            'id',
            'working_days',
            'periods_per_day',
            'period_duration',
            'school_start_time',
            'school_end_time',
            'lunch_duration',
            'lunch_start_after_period',
            'max_same_subject_per_day',
            'max_same_subject_per_week',
            'auto_generate',
            'total_periods_per_week',
            'period_times',
            'updated_by_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id', 'school', 'created_at', 'updated_at', 'updated_by',
            'total_periods_per_week', 'period_times', 'updated_by_name'
        ]

    def get_total_periods_per_week(self, obj):
        return obj.get_total_periods_per_week()

    def get_period_times(self, obj):
        return obj.get_period_times()

    def get_updated_by_name(self, obj):
        if obj.updated_by:
            return f"{obj.updated_by.first_name} {obj.updated_by.last_name}".strip() or obj.updated_by.email
        return None


class TimetableSettingsCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for INITIAL CREATION of timetable settings.
    ALL fields are required - no defaults.
    """
    class Meta:
        model = TimetableSettings
        fields = [
            'working_days',
            'periods_per_day',
            'period_duration',
            'school_start_time',
            'school_end_time',
            'lunch_duration',
            'lunch_start_after_period',
            'max_same_subject_per_day',
            'max_same_subject_per_week',
            'auto_generate',
        ]

    def validate(self, attrs):
        # Validate periods_per_day
        periods = attrs.get('periods_per_day')
        if periods < 1:
            raise serializers.ValidationError({"periods_per_day": "Must be at least 1."})
        if periods > 15:
            raise serializers.ValidationError({"periods_per_day": "Cannot exceed 15 periods per day."})

        # Validate period_duration
        duration = attrs.get('period_duration')
        if duration < 15:
            raise serializers.ValidationError({"period_duration": "Period duration must be at least 15 minutes."})
        if duration > 120:
            raise serializers.ValidationError({"period_duration": "Period duration cannot exceed 120 minutes."})

        # Validate working days
        working_days = attrs.get('working_days')
        if not working_days:
            raise serializers.ValidationError({"working_days": "At least one working day is required."})
        
        valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for day in working_days:
            if day not in valid_days:
                raise serializers.ValidationError(
                    {"working_days": f"Invalid day: {day}. Must be one of {valid_days}."}
                )

        # Validate lunch position
        lunch_after = attrs.get('lunch_start_after_period')
        periods_per_day = attrs.get('periods_per_day')

        if lunch_after >= periods_per_day:
            raise serializers.ValidationError(
                {"lunch_start_after_period": "Lunch must occur before the end of the school day."}
            )

        # Validate school hours
        start_time = attrs.get('school_start_time')
        end_time = attrs.get('school_end_time')
        if start_time >= end_time:
            raise serializers.ValidationError(
                {"school_end_time": "School end time must be after start time."}
            )

        # Calculate total time needed
        total_period_time = periods * duration
        lunch_time = attrs.get('lunch_duration')
        total_time_needed = total_period_time + lunch_time
        
        # Convert to minutes
        start_minutes = start_time.hour * 60 + start_time.minute
        end_minutes = end_time.hour * 60 + end_time.minute
        available_time = end_minutes - start_minutes
        
        if total_time_needed > available_time:
            raise serializers.ValidationError(
                {"period_duration": f"Total time needed ({total_time_needed} mins) exceeds available time ({available_time} mins). Reduce periods, duration, or increase school hours."}
            )

        return attrs


class TimetableSettingsUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for UPDATING timetable settings.
    All fields are required but you can partially update.
    """
    class Meta:
        model = TimetableSettings
        fields = [
            'working_days',
            'periods_per_day',
            'period_duration',
            'school_start_time',
            'school_end_time',
            'lunch_duration',
            'lunch_start_after_period',
            'max_same_subject_per_day',
            'max_same_subject_per_week',
            'auto_generate',
        ]

    def validate(self, attrs):
        # Same validation as create
        periods = attrs.get('periods_per_day')
        if periods and periods < 1:
            raise serializers.ValidationError({"periods_per_day": "Must be at least 1."})
        if periods and periods > 15:
            raise serializers.ValidationError({"periods_per_day": "Cannot exceed 15 periods per day."})

        duration = attrs.get('period_duration')
        if duration and duration < 15:
            raise serializers.ValidationError({"period_duration": "Period duration must be at least 15 minutes."})
        if duration and duration > 120:
            raise serializers.ValidationError({"period_duration": "Period duration cannot exceed 120 minutes."})

        working_days = attrs.get('working_days')
        if working_days:
            if not working_days:
                raise serializers.ValidationError({"working_days": "At least one working day is required."})
            valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            for day in working_days:
                if day not in valid_days:
                    raise serializers.ValidationError(
                        {"working_days": f"Invalid day: {day}. Must be one of {valid_days}."}
                    )

        lunch_after = attrs.get('lunch_start_after_period')
        periods_per_day = attrs.get('periods_per_day')
        if lunch_after and periods_per_day:
            if lunch_after >= periods_per_day:
                raise serializers.ValidationError(
                    {"lunch_start_after_period": "Lunch must occur before the end of the school day."}
                )

        start_time = attrs.get('school_start_time')
        end_time = attrs.get('school_end_time')
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError(
                {"school_end_time": "School end time must be after start time."}
            )

        # Calculate time if all needed fields are present
        if periods and duration and start_time and end_time and attrs.get('lunch_duration'):
            total_period_time = periods * duration
            lunch_time = attrs.get('lunch_duration')
            total_time_needed = total_period_time + lunch_time
            
            start_minutes = start_time.hour * 60 + start_time.minute
            end_minutes = end_time.hour * 60 + end_time.minute
            available_time = end_minutes - start_minutes
            
            if total_time_needed > available_time:
                raise serializers.ValidationError(
                    {"period_duration": f"Total time needed ({total_time_needed} mins) exceeds available time ({available_time} mins)."}
                )

        return attrs


class TimetableSettingsHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for timetable settings change history.
    """
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TimetableConfigHistory
        fields = ['id', 'changed_by', 'changed_by_name', 'changed_at', 'changes']
        read_only_fields = ['id', 'changed_by', 'changed_at', 'changes']

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            return f"{obj.changed_by.first_name} {obj.changed_by.last_name}".strip() or obj.changed_by.email
        return None


class TimetableSettingsCheckSerializer(serializers.Serializer):
    """
    Check if settings exist and return status.
    """
    exists = serializers.BooleanField()
    has_settings = serializers.BooleanField()
    message = serializers.CharField()