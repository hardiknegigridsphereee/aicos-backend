# core/serializers.py
from rest_framework import serializers


class FileUploadRequestSerializer(serializers.Serializer):
    """Serializer for file upload request"""
    file_type = serializers.ChoiceField(choices=['profile_picture', 'assignment_submission'])
    file_name = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=100, required=False)
    student_id = serializers.UUIDField(required=False)  # For parent/teacher uploading on behalf of student


class FileUploadResponseSerializer(serializers.Serializer):
    """Serializer for file upload response"""
    upload_url = serializers.URLField()
    file_id = serializers.CharField()
    file_path = serializers.CharField()
    expires_at = serializers.DateTimeField()
    expires_in = serializers.IntegerField()
    file_url = serializers.URLField(required=False)  # Download URL after upload