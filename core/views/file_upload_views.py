# core/views/file_upload_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.conf import settings
from datetime import datetime
from ..utils.r2_storage import r2_storage
from ..serializers import FileUploadRequestSerializer
from profiles.models import StudentProfile, TeacherProfile, ParentProfile
from operations.models import Assignment, StudentSubmission
import os
import traceback


class GenerateUploadURLView(APIView):
    """
    POST /api/v1/uploads/generate-url/
    Generates a signed URL for file upload
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FileUploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        file_type = serializer.validated_data['file_type']
        file_name = serializer.validated_data['file_name']
        content_type = serializer.validated_data.get('content_type', 'application/octet-stream')
        student_id = serializer.validated_data.get('student_id')
        
        user = request.user
        school = user.school
        
        # Determine file path based on type and user
        file_path = self._get_file_path(user, school, file_type, file_name, student_id)
        
        # Generate upload URL
        upload_data = r2_storage.generate_upload_url(file_path, content_type)
        
        # If using R2, add the public URL for after upload
        if settings.DEFAULT_FILE_STORAGE == 'storages.backends.s3boto3.S3Boto3Storage':
            upload_data['file_url'] = f"{settings.MEDIA_URL}{upload_data['file_path']}"
        
        return Response(upload_data, status=status.HTTP_200_OK)

    def _get_file_path(self, user, school, file_type, file_name, student_id=None):
        """
        Determine the file path based on type and user.
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{file_name}"
        
        if file_type == 'profile_picture':
            try:
                if student_id:
                    student = StudentProfile.objects.get(id=student_id, school=school)
                else:
                    student = StudentProfile.objects.get(user=user, school=school)
                return f"profiles/pictures/{student.id}/{filename}"
            except StudentProfile.DoesNotExist:
                raise ValidationError("Student profile not found")
                
        elif file_type == 'assignment_submission':
            try:
                if student_id:
                    student = StudentProfile.objects.get(id=student_id, school=school)
                    
                    # Verify teacher is assigned to this student
                    if hasattr(user, 'teacherprofile'):
                        pass
                    
                    # Verify parent has permission
                    if hasattr(user, 'parentprofile'):
                        from profiles.models import ParentStudentMapping
                        if not ParentStudentMapping.objects.filter(
                            parent=user.parentprofile,
                            student=student,
                            can_view_academics=True
                        ).exists():
                            raise ValidationError("Parent not authorized for this student")
                else:
                    student = StudentProfile.objects.get(user=user, school=school)
                
                return f"submissions/{student.id}/{filename}"
            except StudentProfile.DoesNotExist:
                raise ValidationError("Student profile not found")
        
        raise ValidationError("Invalid file type")


class ConfirmUploadView(APIView):
    """
    POST /api/v1/uploads/confirm/
    Confirms that a file was uploaded successfully
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file_path = request.data.get('file_path')
        file_type = request.data.get('file_type')
        reference_id = request.data.get('reference_id')
        
        if not file_path:
            return Response(
                {"detail": "file_path is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Verify file exists in R2
        if not r2_storage.confirm_upload(file_path):
            return Response(
                {"detail": "File upload could not be verified"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get file URL
        file_url = f"{settings.MEDIA_URL}{file_path}"
        
        # Direct DB update if reference_id is provided
        if file_type == 'assignment_submission' and reference_id:
            try:
                submission = StudentSubmission.objects.get(id=reference_id)
                submission.file = file_path
                submission.status = 'Submitted'
                submission.save(update_fields=['file', 'status'])
            except StudentSubmission.DoesNotExist:
                pass
        
        return Response({
            "detail": "File uploaded successfully",
            "file_path": file_path,
            "file_url": file_url
        }, status=status.HTTP_200_OK)


class GenerateDownloadURLView(APIView):
    """
    GET /api/v1/uploads/download-url/?file_path=<path>
    Generates a signed URL for downloading a file
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        file_path = request.query_params.get('file_path')
        
        if not file_path:
            return Response(
                {"detail": "file_path is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        download_data = r2_storage.generate_download_url(file_path)
        
        return Response(download_data, status=status.HTTP_200_OK)


class GenerateViewURLView(APIView):
    """
    GET /api/v1/uploads/view-url/?file_path=<path>
    Generates a signed URL for viewing a file in the browser (inline)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        file_path = request.query_params.get('file_path')
        filename = request.query_params.get('filename')
        
        if not file_path:
            return Response(
                {"detail": "file_path is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate view URL with inline disposition
        view_data = r2_storage.generate_view_url(
            file_path=file_path,
            filename=filename,
            expires_in=3600  # 1 hour
        )
        
        return Response(view_data, status=status.HTTP_200_OK)


class GenerateProfileImageUploadURLView(APIView):
    """
    POST /api/v1/uploads/profile-image/
    Generate upload URL for profile picture (Parent, Student, or Teacher)
    
    Request: { 
        "file_name": "photo.jpg", 
        "content_type": "image/jpeg",
        "profile_type": "parent" | "student" | "teacher"
    }
    Response: { "upload_url": "...", "file_path": "...", "file_id": "..." }
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        file_name = request.data.get('file_name')
        content_type = request.data.get('content_type', 'image/jpeg')
        profile_type = request.data.get('profile_type', 'parent')
        
        if not file_name:
            return Response(
                {"detail": "file_name is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate that it's an image
        if not content_type.startswith('image/'):
            return Response(
                {"detail": "Only image uploads are allowed. Content-Type must be image/*"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate profile type
        valid_types = ['parent', 'student', 'teacher']
        if profile_type not in valid_types:
            return Response(
                {"detail": f"profile_type must be one of: {', '.join(valid_types)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user has the correct profile
        profile_map = {
            'parent': ('parentprofile', ParentProfile),
            'student': ('studentprofile', StudentProfile),
            'teacher': ('teacherprofile', TeacherProfile),
        }
        
        profile_attr, profile_model = profile_map[profile_type]
        
        if not hasattr(request.user, profile_attr):
            return Response(
                {"detail": f"You don't have a {profile_type} profile"},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Generate upload URL with dynamic path based on profile type
            upload_data = r2_storage.generate_image_upload_url(
                user_id=request.user.id,
                file_name=file_name,
                content_type=content_type,
                folder=f"profiles/{profile_type}s"
            )
            
            return Response({
                "upload_url": upload_data['url'],
                "file_path": upload_data['file_path'],
                "file_id": upload_data['file_id'],
                "expires_at": upload_data['expires_at'],
                "expires_in": upload_data['expires_in'],
                "profile_type": profile_type
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            traceback.print_exc()
            return Response({
                "detail": f"Failed to generate upload URL: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetProfilePictureView(APIView):
    """
    GET /api/v1/profiles/me/picture/?profile_type=parent|student|teacher
    Returns a signed URL for the user's profile picture
    
    Response: {
        "url": "https://ai-cos.r2...signed...url",
        "expires_at": "2026-06-24T06:45:00Z",
        "expires_in": 86400,
        "has_picture": true,
        "profile_type": "parent"
    }
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        profile_type = request.query_params.get('profile_type', 'parent')
        
        # Validate profile type
        valid_types = ['parent', 'student', 'teacher']
        if profile_type not in valid_types:
            return Response({
                "has_picture": False,
                "detail": f"profile_type must be one of: {', '.join(valid_types)}",
                "url": None,
                "expires_at": None,
                "expires_in": None
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get the profile
        profile_map = {
            'parent': ('parentprofile', ParentProfile),
            'student': ('studentprofile', StudentProfile),
            'teacher': ('teacherprofile', TeacherProfile),
        }
        
        profile_attr, profile_model = profile_map[profile_type]
        
        if not hasattr(request.user, profile_attr):
            return Response({
                "has_picture": False,
                "detail": f"You don't have a {profile_type} profile",
                "url": None,
                "expires_at": None,
                "expires_in": None
            }, status=status.HTTP_403_FORBIDDEN)
        
        profile = getattr(request.user, profile_attr)
        
        # Get the picture path properly
        picture_path = None
        
        if hasattr(profile, 'profile_picture'):
            if isinstance(profile.profile_picture, str):
                picture_path = profile.profile_picture
            elif hasattr(profile.profile_picture, 'name'):
                picture_path = profile.profile_picture.name
            else:
                picture_path = str(profile.profile_picture) if profile.profile_picture else None
        
        if not picture_path:
            return Response({
                "has_picture": False,
                "detail": "No profile picture set",
                "url": None,
                "expires_at": None,
                "expires_in": None,
                "profile_type": profile_type
            }, status=status.HTTP_200_OK)
        
        try:
            picture_path = str(picture_path)
            
            # Generate a signed view URL (valid for 24 hours)
            view_data = r2_storage.generate_view_url(
                file_path=picture_path,
                expires_in=86400  # 24 hours
            )
            
            return Response({
                "has_picture": True,
                "url": view_data['url'],
                "expires_at": view_data['expires_at'],
                "expires_in": view_data['expires_in'],
                "file_path": picture_path,
                "profile_type": profile_type
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            traceback.print_exc()
            return Response({
                "has_picture": False,
                "detail": f"Failed to generate view URL: {str(e)}",
                "url": None,
                "expires_at": None,
                "expires_in": None,
                "profile_type": profile_type
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)