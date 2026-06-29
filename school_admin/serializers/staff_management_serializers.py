# school_admin/serializers/staff_management_serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from profiles.models import TeacherProfile, StudentProfile,ParentProfile

User = get_user_model()

# Rename your existing class to match the import expectation
class TeacherOnboardingSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)

    class Meta:
        model = TeacherProfile
        fields = ['id', 'employee_id', 'qualification', 'joining_date', 'first_name', 'last_name', 'email']

    def create(self, validated_data):
        email = validated_data.pop('email')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        school = self.context['request'].user.school

        with transaction.atomic():
            user = User.objects.create_user(email=email, password="TemporaryPassword123!", first_name=first_name, last_name=last_name, school=school)
            return TeacherProfile.objects.create(user=user, school=school, **validated_data)

# Add this class so the import error is resolved
class StudentOnboardingSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)

    class Meta:
        model = StudentProfile
        fields = ['id', 'enrollment_number', 'first_name', 'last_name', 'email']

    def create(self, validated_data):
        email = validated_data.pop('email')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        school = self.context['request'].user.school

        with transaction.atomic():
            user = User.objects.create_user(email=email, password="TemporaryPassword123!", first_name=first_name, last_name=last_name, school=school)
            return StudentProfile.objects.create(user=user, school=school, **validated_data)
        

    # school_admin/serializers/staff_management_serializers.py

class ParentOnboardingSerializer(serializers.ModelSerializer):
    first_name = serializers.CharField(write_only=True)
    last_name = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)

    class Meta:
        model = ParentProfile
        fields = ['id', 'first_name', 'last_name', 'email', 'phone_number', 'address', 'occupation', 'emergency_contact_number']

    def create(self, validated_data):
        email = validated_data.pop('email')
        first_name = validated_data.pop('first_name')
        last_name = validated_data.pop('last_name')
        school = self.context['request'].user.school

        with transaction.atomic():
            user = User.objects.create_user(
                email=email, 
                password="TemporaryPassword123!", 
                first_name=first_name, 
                last_name=last_name, 
                school=school
            )
            return ParentProfile.objects.create(user=user, school=school, **validated_data)