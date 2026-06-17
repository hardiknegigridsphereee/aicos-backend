from rest_framework import serializers
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping

class StudentProfileSerializer(serializers.ModelSerializer):
    # 1. Define these fields explicitly WITHOUT a 'source' to bypass the UUID validation bug
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    
    # FIX 1: Removed the read_only=True overrides for address, phone_number, and blood_group.
    # The ModelSerializer will now automatically pick them up as writable fields.

    class Meta:
        model = StudentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

    # FIX 2: Properly indented to_representation so it belongs inside the class
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.user:
            representation['first_name'] = instance.user.first_name
            representation['last_name'] = instance.user.last_name
            representation['email'] = instance.user.email
        return representation

    # FIX 3: Properly indented update so it belongs inside the class
    def update(self, instance, validated_data):
        # Pop the fields out of the payload before Django tries to save them to the Profile model
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)
        email = validated_data.pop('email', None)

        # Save them directly to the underlying User model
        user = instance.user
        if user:
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if email is not None:
                user.email = email
            user.save()
            
        return super().update(instance, validated_data)


class TeacherProfileSerializer(serializers.ModelSerializer):
    # Bypass the read-only blocks
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)

    class Meta:
        model = TeacherProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

    # Send the user data to React on GET
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.user:
            representation['first_name'] = instance.user.first_name
            representation['last_name'] = instance.user.last_name
            representation['email'] = instance.user.email
        return representation

    # Intercept and save the user data on PATCH
    def update(self, instance, validated_data):
        first_name = validated_data.pop('first_name', None)
        last_name = validated_data.pop('last_name', None)
        email = validated_data.pop('email', None)

        user = instance.user
        if user:
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            if email is not None:
                user.email = email
            user.save()
            
        return super().update(instance, validated_data)


class ParentProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = ParentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')


class ParentStudentMappingSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.user.first_name', read_only=True)
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)

    class Meta:
        model = ParentStudentMapping
        fields = '__all__'
        read_only_fields = ('school', 'id')
        