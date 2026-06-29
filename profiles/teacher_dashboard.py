# profiles/teacher_dashboard.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count

from .models import TeacherProfile
from academics.models import TeacherAssignment, StudentEnrollment
from operations.models import Attendance, StudentSubmission


class TeacherDashboardAPIView(APIView):
    """
    GET /api/v1/profiles/teachers/dashboard/
    Returns comprehensive dashboard for teacher with all classes
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all teaching assignments
        assignments = TeacherAssignment.objects.filter(
            teacher=teacher,
            school=request.user.school
        ).select_related('academic_year', 'class_level', 'section', 'subject')

        # Get current academic year
        current_academic_year = assignments.filter(
            academic_year__start_date__lte=timezone.now().date(),
            academic_year__end_date__gte=timezone.now().date()
        ).first()

        # Total students across all sections
        total_students = 0
        sections_data = []
        
        for assignment in assignments:
            enrollments = StudentEnrollment.objects.filter(
                school=request.user.school,
                section=assignment.section,
                academic_year=assignment.academic_year
            )
            student_count = enrollments.count()
            total_students += student_count
            
            # Get today's attendance for this section
            today = timezone.now().date()
            today_attendance = Attendance.objects.filter(
                school=request.user.school,
                section=assignment.section,
                date=today
            )
            present_count = today_attendance.filter(status__in=['Present', 'Late']).count()
            
            sections_data.append({
                "section_id": str(assignment.section.id),
                "section_name": assignment.section.name,
                "class_level": assignment.class_level.name,
                "subject": assignment.subject.name,
                "subject_id": str(assignment.subject.id),
                "student_count": student_count,
                "today_attendance": {
                    "present": present_count,
                    "total": student_count,
                    "percentage": round((present_count / student_count) * 100, 2) if student_count > 0 else 0
                },
                "is_class_teacher": assignment.is_class_teacher
            })

        # Recent activity (last 7 days)
        last_week = timezone.now() - timedelta(days=7)
        recent_submissions = StudentSubmission.objects.filter(
            school=request.user.school,
            assignment__teacher=teacher,
            submitted_at__gte=last_week
        ).count()

        pending_grading = StudentSubmission.objects.filter(
            school=request.user.school,
            assignment__teacher=teacher,
            grade__isnull=True,
            status='Submitted'
        ).count()

        # Today's classes
        today_classes = len(sections_data)

        return Response({
            "teacher": {
                "id": str(teacher.id),
                "name": f"{teacher.user.first_name} {teacher.user.last_name}",
                "email": teacher.user.email,
                "employee_id": teacher.employee_id
            },
            "summary": {
                "total_classes": len(sections_data),
                "total_students": total_students,
                "today_classes": today_classes,
                "pending_grading": pending_grading,
                "recent_submissions": recent_submissions,
                "current_academic_year": current_academic_year.academic_year.name if current_academic_year else None
            },
            "sections": sections_data,
            "last_updated": timezone.now()
        })