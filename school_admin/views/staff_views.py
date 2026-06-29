# school_admin/views/staff_views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from school_admin.serializers.staff_management_serializers import (
    StudentOnboardingSerializer, TeacherOnboardingSerializer,ParentOnboardingSerializer
)

class OnboardStudentAPIView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentOnboardingSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Student registered successfully"}, status=status.HTTP_201_CREATED)

class OnboardTeacherAPIView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TeacherOnboardingSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Teacher registered successfully"}, status=status.HTTP_201_CREATED)
    
# school_admin/views/staff_views.py

class OnboardParentAPIView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ParentOnboardingSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "Parent registered successfully"}, status=status.HTTP_201_CREATED)