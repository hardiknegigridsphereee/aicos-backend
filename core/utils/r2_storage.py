# core/utils/r2_storage.py
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
import uuid
from datetime import datetime, timedelta
import os


class R2Storage:
    """Handles R2/S3 operations with signed URLs"""
    
    def __init__(self):
        self.client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
            config=Config(signature_version='s3v4')
        )
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME

    def generate_upload_url(self, file_path, content_type=None, expires_in=900):
        """
        Generate a signed URL for uploading a file.
        
        Args:
            file_path (str): The path where file will be stored
            content_type (str): MIME type of the file (optional but recommended)
            expires_in (int): URL expiration time in seconds (default: 15 minutes)
        
        Returns:
            dict: {
                'url': signed URL for upload,
                'file_id': unique file identifier,
                'expires_at': expiration timestamp,
                'expires_in': expiration time in seconds,
                'file_path': the full path in bucket
            }
        """
        try:
            # Generate a unique file ID
            file_id = str(uuid.uuid4())
            
            # Extract file extension if present
            extension = os.path.splitext(file_path)[1]
            
            # Create unique filename
            unique_filename = f"{file_id}{extension}"
            
            # Full path in bucket (preserve directory structure)
            directory = os.path.dirname(file_path)
            if directory:
                full_path = f"{directory}/{unique_filename}"
            else:
                full_path = unique_filename

            # Generate presigned URL
            url = self.client.generate_presigned_url(
                ClientMethod='put_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': full_path,
                    'ContentType': content_type or 'application/octet-stream',
                },
                ExpiresIn=expires_in
            )

            return {
                'url': url,
                'file_id': file_id,
                'file_path': full_path,
                'expires_at': datetime.now() + timedelta(seconds=expires_in),
                'expires_in': expires_in
            }
            
        except ClientError as e:
            raise Exception(f"Failed to generate upload URL: {str(e)}")

    def generate_image_upload_url(self, user_id, file_name, content_type="image/jpeg", folder="profiles"):
        """
        Generate a signed URL for uploading a profile image.
        Simple path: profiles/parents/parent_{user_id}/{filename}
        
        Args:
            user_id (str): The user's UUID
            file_name (str): The original filename
            content_type (str): MIME type of the image (default: image/jpeg)
            folder (str): The folder path (default: "profiles")
        
        Returns:
            dict: {
                'url': signed upload URL,
                'file_path': path in bucket,
                'file_id': unique file ID,
                'expires_at': expiration timestamp,
                'expires_in': expiration time in seconds
            }
        """
        # Clean filename
        extension = os.path.splitext(file_name)[1] or '.jpg'
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d')
        
        # Simple path structure
        clean_filename = f"{timestamp}_{unique_id}{extension}"
        file_path = f"{folder}/parent_{user_id}/{clean_filename}"
        
        # Generate upload URL with dynamic content type
        return self.generate_upload_url(
            file_path=file_path,
            content_type=content_type,
            expires_in=900  # 15 minutes
        )

    def get_image_view_url(self, file_path, expires_in=86400):
        """
        Get a view URL for an image (24 hours default)
        
        Args:
            file_path (str): The path of the file in bucket
            expires_in (int): URL expiration time in seconds (default: 24 hours)
        
        Returns:
            dict: {
                'url': signed view URL,
                'expires_at': expiration timestamp,
                'expires_in': expiration time in seconds
            }
        """
        return self.generate_view_url(
            file_path=file_path,
            expires_in=expires_in
        )

    def generate_download_url(self, file_path, expires_in=3600):
        """
        Generate a signed URL for downloading a file.
        
        Args:
            file_path (str): The path of the file in bucket
            expires_in (int): URL expiration time in seconds (default: 1 hour)
        
        Returns:
            dict: {
                'url': signed download URL,
                'expires_at': expiration timestamp
            }
        """
        try:
            url = self.client.generate_presigned_url(
                ClientMethod='get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_path,
                    'ResponseContentDisposition': f'attachment; filename="{os.path.basename(file_path)}"',
                },
                ExpiresIn=expires_in
            )

            return {
                'url': url,
                'expires_at': datetime.now() + timedelta(seconds=expires_in),
                'expires_in': expires_in
            }
            
        except ClientError as e:
            raise Exception(f"Failed to generate download URL: {str(e)}")

    def generate_view_url(self, file_path, filename=None, expires_in=3600):
        """
        Generate a signed URL for viewing a file in the browser (inline).
        
        Args:
            file_path (str): The path of the file in bucket
            filename (str): Original filename for Content-Disposition (optional)
            expires_in (int): URL expiration time in seconds (default: 1 hour)
        
        Returns:
            dict: {
                'url': signed view URL,
                'expires_at': expiration timestamp,
                'expires_in': expiration time in seconds
            }
        """
        try:
            params = {
                'Bucket': self.bucket_name,
                'Key': file_path,
            }
            
            # Set Content-Disposition to "inline" for viewing in browser
            if filename:
                params['ResponseContentDisposition'] = f'inline; filename="{filename}"'
            else:
                params['ResponseContentDisposition'] = 'inline'
            
            url = self.client.generate_presigned_url(
                ClientMethod='get_object',
                Params=params,
                ExpiresIn=expires_in
            )

            return {
                'url': url,
                'expires_at': datetime.now() + timedelta(seconds=expires_in),
                'expires_in': expires_in
            }
            
        except ClientError as e:
            raise Exception(f"Failed to generate view URL: {str(e)}")

    def confirm_upload(self, file_path):
        """
        Verify that a file was uploaded successfully.
        """
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        except ClientError:
            return False

    def delete_file(self, file_path):
        """
        Delete a file from R2.
        """
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            return True
        except ClientError as e:
            raise Exception(f"Failed to delete file: {str(e)}")


# Singleton instance
r2_storage = R2Storage()