# profiles/student_dashboard.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.db.models import Count, Q, Avg
from django.utils import timezone
from datetime import timedelta

from .models import StudentProfile
from academics.models import StudentEnrollment
from operations.models import Attendance, StudentGrade, Assignment, StudentSubmission


class StudentDashboardAPIView(APIView):
    """
    GET /api/v1/profiles/students/dashboard/
    Returns comprehensive dashboard data for the current student.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get current enrollment
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        # 1. Attendance Summary (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        attendance_records = Attendance.objects.filter(
            student=student,
            school=request.user.school,
            date__gte=thirty_days_ago
        )
        
        total_attendance = attendance_records.count()
        present_count = attendance_records.filter(status__in=['Present', 'Late']).count()
        attendance_percentage = round((present_count / total_attendance) * 100, 2) if total_attendance > 0 else 0

        # 2. Upcoming Assignments (next 7 days)
        next_week = timezone.now() + timedelta(days=7)
        upcoming_assignments = []
        if enrollment:
            assignments = Assignment.objects.filter(
                school=request.user.school,
                section=enrollment.section,
                due_date__gte=timezone.now(),
                due_date__lte=next_week
            ).order_by('due_date')[:5]
            
            for assignment in assignments:
                # Check if submitted
                submitted = StudentSubmission.objects.filter(
                    assignment=assignment,
                    student=student
                ).exists()
                
                upcoming_assignments.append({
                    "id": str(assignment.id),
                    "title": assignment.title,
                    "subject": assignment.subject.name,
                    "due_date": assignment.due_date,
                    "submitted": submitted
                })

        # 3. Recent Grades (last 5)
        recent_grades = StudentGrade.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('exam', 'subject').order_by('-exam__start_date')[:5]

        grades_data = []
        for grade in recent_grades:
            grades_data.append({
                "subject": grade.subject.name,
                "exam": grade.exam.name,
                "marks": float(grade.marks_obtained),
                "max_marks": float(grade.max_marks),
                "percentage": round((grade.marks_obtained / grade.max_marks) * 100, 2) if grade.max_marks > 0 else 0
            })

        # 4. Class Info
        class_info = None
        if enrollment:
            class_info = {
                "class": enrollment.class_level.name,
                "section": enrollment.section.name,
                "academic_year": enrollment.academic_year.name,
                "roll_number": enrollment.roll_number
            }

        response_data = {
            "student": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "email": student.user.email,
                "enrollment_number": student.enrollment_number,
                "profile_picture": student.profile_picture.url if student.profile_picture else None
            },
            "class_info": class_info,
            "attendance": {
                "total_days": total_attendance,
                "present_days": present_count,
                "attendance_percentage": attendance_percentage,
                "status": "Excellent" if attendance_percentage >= 90 else "Good" if attendance_percentage >= 75 else "Needs Attention"
            },
            "upcoming_assignments": upcoming_assignments,
            "recent_grades": grades_data,
            "stats": {
                "total_assignments": Assignment.objects.filter(section=enrollment.section).count() if enrollment else 0,
                "total_exams": 0,
                "total_grades": StudentGrade.objects.filter(student=student).count()
            }
        }

        return Response(response_data)