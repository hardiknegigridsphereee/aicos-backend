from rest_framework import serializers
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping

class StudentProfileSerializer(serializers.ModelSerializer):

    # 1. Define these fields explicitly WITHOUT a 'source' to bypass the UUID validation bug
        first_name = serializers.CharField(required=False)
        last_name = serializers.CharField(required=False)
        email = serializers.EmailField(required=False)
        
        # New fields brought in from the team's updates
        address = serializers.CharField(read_only=True)
        phone_number = serializers.CharField(read_only=True)
        blood_group = serializers.CharField(read_only=True)
        class Meta:
            model = StudentProfile
            fields = '__all__'
            read_only_fields = ('school', 'id')

    # 2. This populates the fields dynamically when React asks for the student data (GET)
def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.user:
            representation['first_name'] = instance.user.first_name
            representation['last_name'] = instance.user.last_name
            representation['email'] = instance.user.email
        return representation

    # 3. This intercepts the flat fields when React updates the student data (PATCH)
def update(self, instance, validated_data):
        # Pop the fields out of the payload before Django tries to save them to the Profile model
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

class TeacherProfileSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)

    class Meta:
        model = TeacherProfile
        fields = '__all__'
        read_only_fields = ('school', 'id')

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
