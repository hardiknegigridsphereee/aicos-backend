# profiles/parent_additions.py
# Add these methods to parent_dashboard.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .models import ParentProfile, ParentStudentMapping
from academics.models import StudentEnrollment
from operations.models import Assignment, StudentSubmission
from operations.serializers import AssignmentWithStatusSerializer, StudentSubmissionSerializer


class ParentChildAssignmentsAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/{child_id}/assignments/
    Returns assignments for a specific child with submission status
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, child_id):
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify parent-child relationship
        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=child_id,
                school=request.user.school,
                can_view_academics=True
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to view this child's data."},
                status=status.HTTP_403_FORBIDDEN
            )

        student = mapping.student
        
        # Get current enrollment
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response({
                "count": 0,
                "results": []
            })

        # Get assignments for this section
        assignments = Assignment.objects.filter(
            school=request.user.school,
            section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')

        # Annotate with submission status
        serializer = AssignmentWithStatusSerializer(
            assignments, 
            many=True, 
            context={'student_id': str(student.id)}
        )

        return Response({
            "child": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "enrollment_number": student.enrollment_number
            },
            "count": assignments.count(),
            "results": serializer.data
        })


class ParentChildSubmissionsAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/{child_id}/submissions/
    Returns submissions for a specific child
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, child_id):
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify parent-child relationship
        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=child_id,
                school=request.user.school,
                can_view_academics=True
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to view this child's data."},
                status=status.HTTP_403_FORBIDDEN
            )

        student = mapping.student
        
        # Get submissions
        submissions = StudentSubmission.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('assignment', 'assignment__subject', 'assignment__section')\
         .order_by('-submitted_at')

        serializer = StudentSubmissionSerializer(submissions, many=True)

        return Response({
            "child": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "enrollment_number": student.enrollment_number
            },
            "count": submissions.count(),
            "results": serializer.data
        })