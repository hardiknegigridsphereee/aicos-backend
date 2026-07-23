from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.db import transaction
from profiles.models import TeacherProfile, StudentProfile, ParentProfile

from school_admin.utils.email import send_registration_email

User = get_user_model()

TEMPORARY_PASSWORD = "TemporaryPassword123!"


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
            user = User.objects.create_user(
                email=email, password=TEMPORARY_PASSWORD,
                first_name=first_name, last_name=last_name, school=school
            )
            profile = TeacherProfile.objects.create(user=user, school=school, **validated_data)
            transaction.on_commit(
                lambda: send_registration_email(user, 'teacher', TEMPORARY_PASSWORD)
            )
            return profile


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
            user = User.objects.create_user(
                email=email, password=TEMPORARY_PASSWORD,
                first_name=first_name, last_name=last_name, school=school
            )
            profile = StudentProfile.objects.create(user=user, school=school, **validated_data)
            transaction.on_commit(
                lambda: send_registration_email(user, 'student', TEMPORARY_PASSWORD)
            )
            return profile


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
                password=TEMPORARY_PASSWORD,
                first_name=first_name,
                last_name=last_name,
                school=school
            )
            profile = ParentProfile.objects.create(user=user, school=school, **validated_data)
            transaction.on_commit(
                lambda: send_registration_email(user, 'parent', TEMPORARY_PASSWORD)
            )
            return profile