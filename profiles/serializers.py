# profiles/serializers.py
from rest_framework import serializers
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping


class StudentProfileSerializer(serializers.ModelSerializer):
    # Define these fields explicitly to handle User model fields
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    
    # Profile fields - writable (required=False for partial updates)
    address = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False)
    blood_group = serializers.CharField(required=False)
    
    # ✅ Handle string paths for profile_picture
    profile_picture = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    
    class Meta:
        model = StudentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

    def to_representation(self, instance):
        """Populate User fields when sending response"""
        representation = super().to_representation(instance)
        if instance.user:
            representation['first_name'] = instance.user.first_name
            representation['last_name'] = instance.user.last_name
            representation['email'] = instance.user.email
        
        # ✅ Convert ImageFieldFile to string for profile_picture
        if instance.profile_picture:
            if hasattr(instance.profile_picture, 'name'):
                representation['profile_picture'] = instance.profile_picture.name
            else:
                representation['profile_picture'] = str(instance.profile_picture)
        else:
            representation['profile_picture'] = None
            
        return representation

    def update(self, instance, validated_data):
        """Handle User fields and profile_picture when updating"""
        # Handle User fields
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
        
        # ✅ Handle profile_picture as a string path
        if 'profile_picture' in validated_data:
            profile_picture_value = validated_data.pop('profile_picture')
            if profile_picture_value is not None:
                instance.profile_picture = profile_picture_value
            
        return super().update(instance, validated_data)


class TeacherProfileSerializer(serializers.ModelSerializer):
    # User fields
    first_name = serializers.CharField(required=False)
    last_name = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    
    # ✅ Handle string paths for profile_picture
    profile_picture = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = TeacherProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

    def to_representation(self, instance):
        """Populate User fields when sending response"""
        representation = super().to_representation(instance)
        if instance.user:
            representation['first_name'] = instance.user.first_name
            representation['last_name'] = instance.user.last_name
            representation['email'] = instance.user.email
            representation['is_archived'] = not instance.user.is_active
        
        # ✅ Convert ImageFieldFile to string for profile_picture
        if instance.profile_picture:
            if hasattr(instance.profile_picture, 'name'):
                representation['profile_picture'] = instance.profile_picture.name
            else:
                representation['profile_picture'] = str(instance.profile_picture)
        else:
            representation['profile_picture'] = None
            
        return representation

    def update(self, instance, validated_data):
        """Handle User fields and profile_picture when updating"""
        # Handle User fields
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
        
        # ✅ Handle profile_picture as a string path
        if 'profile_picture' in validated_data:
            profile_picture_value = validated_data.pop('profile_picture')
            if profile_picture_value is not None:
                instance.profile_picture = profile_picture_value
            
        return super().update(instance, validated_data)


class ParentProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    
    # Handle string paths for profile_picture
    profile_picture = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = ParentProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.user:
            representation['is_archived'] = not instance.user.is_active
        
        # ✅ Convert ImageFieldFile to string for profile_picture
        if instance.profile_picture:
            if hasattr(instance.profile_picture, 'name'):
                representation['profile_picture'] = instance.profile_picture.name
            else:
                representation['profile_picture'] = str(instance.profile_picture)
        else:
            representation['profile_picture'] = None
            
        return representation

    def update(self, instance, validated_data):
        # Handle profile_picture as a string path
        if 'profile_picture' in validated_data:
            profile_picture_value = validated_data.pop('profile_picture')
            if profile_picture_value is not None:
                # Set the value directly on the instance
                instance.profile_picture = profile_picture_value
        
        # Update other fields
        return super().update(instance, validated_data)


class ParentStudentMappingSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.user.first_name', read_only=True)
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)

    class Meta:
        model = ParentStudentMapping
        fields = '__all__'
        read_only_fields = ('school', 'id')