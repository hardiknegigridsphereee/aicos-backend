# profiles/parent_dashboard.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Avg, Q

from .models import ParentProfile, ParentStudentMapping
from academics.models import StudentEnrollment
from operations.models import Attendance, StudentGrade, Assignment, StudentSubmission, Exam


class ParentDashboardAPIView(APIView):
    """
    GET /api/v1/profiles/parents/dashboard/
    Returns comprehensive dashboard for parent with all children
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all children
        mappings = ParentStudentMapping.objects.filter(
            parent=parent,
            school=request.user.school
        ).select_related('student__user')

        children_data = []
        for mapping in mappings:
            student = mapping.student
            child_data = self._get_child_dashboard_data(student)
            children_data.append({
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "email": student.user.email,
                "enrollment_number": student.enrollment_number,
                "relationship": mapping.relationship,
                "is_primary_contact": mapping.is_primary_contact,
                "can_view_academics": mapping.can_view_academics,
                "can_pay_fees": mapping.can_pay_fees,
                "dashboard": child_data
            })

        return Response({
            "parent": {
                "id": str(parent.id),
                "name": f"{parent.user.first_name} {parent.user.last_name}",
                "email": parent.user.email,
                "phone": parent.phone_number
            },
            "total_children": len(children_data),
            "children": children_data,
            "last_updated": timezone.now()
        })

    def _get_child_dashboard_data(self, student):
        """Helper method to get dashboard data for a single child"""
        
        # Get current enrollment
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=student.school
        ).order_by('-academic_year__start_date').first()

        # Attendance Summary (last 30 days)
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        attendance_records = Attendance.objects.filter(
            student=student,
            school=student.school,
            date__gte=thirty_days_ago
        )
        
        total_attendance = attendance_records.count()
        present_count = attendance_records.filter(status__in=['Present', 'Late']).count()
        attendance_percentage = round((present_count / total_attendance) * 100, 2) if total_attendance > 0 else 0

        # Recent Grades (last 5)
        recent_grades = StudentGrade.objects.filter(
            student=student,
            school=student.school
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

        # Upcoming Assignments (next 7 days)
        next_week = timezone.now() + timedelta(days=7)
        upcoming_assignments = []
        if enrollment:
            assignments = Assignment.objects.filter(
                school=student.school,
                section=enrollment.section,
                due_date__gte=timezone.now(),
                due_date__lte=next_week
            ).order_by('due_date')[:5]
            
            for assignment in assignments:
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

        # Upcoming Exams
        upcoming_exams = []
        if enrollment:
            exams = Exam.objects.filter(
                school=student.school,
                academic_year=enrollment.academic_year,
                start_date__gte=timezone.now().date()
            ).order_by('start_date')[:5]
            
            for exam in exams:
                # Check if grades are published for this exam
                grades_published = StudentGrade.objects.filter(
                    student=student,
                    exam=exam
                ).exists()
                
                upcoming_exams.append({
                    "id": str(exam.id),
                    "name": exam.name,
                    "start_date": exam.start_date,
                    "end_date": exam.end_date,
                    "is_published": exam.is_published,
                    "grades_published": grades_published
                })

        # Overall Performance
        all_grades = StudentGrade.objects.filter(
            student=student,
            school=student.school
        )
        total_marks = sum(g.marks_obtained for g in all_grades)
        total_max = sum(g.max_marks for g in all_grades)
        overall_percentage = round((total_marks / total_max) * 100, 2) if total_max > 0 else 0

        return {
            "class_info": {
                "class": enrollment.class_level.name if enrollment else None,
                "section": enrollment.section.name if enrollment else None,
                "academic_year": enrollment.academic_year.name if enrollment else None,
                "roll_number": enrollment.roll_number if enrollment else None
            } if enrollment else None,
            "attendance": {
                "total_days": total_attendance,
                "present_days": present_count,
                "attendance_percentage": attendance_percentage,
                "status": "Excellent" if attendance_percentage >= 90 else "Good" if attendance_percentage >= 75 else "Needs Attention"
            },
            "recent_grades": grades_data,
            "upcoming_assignments": upcoming_assignments,
            "upcoming_exams": upcoming_exams,
            "overall_percentage": overall_percentage,
            "stats": {
                "total_assignments": Assignment.objects.filter(section=enrollment.section).count() if enrollment else 0,
                "total_exams": Exam.objects.filter(academic_year=enrollment.academic_year).count() if enrollment else 0,
                "total_grades": StudentGrade.objects.filter(student=student).count()
            }
        }


class ParentChildDetailAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/{id}/
    Returns detailed data for a specific child
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
                school=request.user.school
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to view this child's data."},
                status=status.HTTP_403_FORBIDDEN
            )

        student = mapping.student
        dashboard_data = ParentDashboardAPIView()._get_child_dashboard_data(student)

        return Response({
            "child": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "email": student.user.email,
                "enrollment_number": student.enrollment_number,
                "date_of_birth": student.date_of_birth,
                "blood_group": student.blood_group,
                "profile_picture": student.profile_picture.url if student.profile_picture else None,
                "relationship": mapping.relationship,
                "is_primary_contact": mapping.is_primary_contact,
                "can_view_academics": mapping.can_view_academics,
                "can_pay_fees": mapping.can_pay_fees
            },
            "dashboard": dashboard_data
        })


class ParentChildAttendanceAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/{id}/attendance/
    Returns attendance details for a specific child
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
                school=request.user.school
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to view this child's data."},
                status=status.HTTP_403_FORBIDDEN
            )

        student = mapping.student
        
        # Get attendance records
        attendance_records = Attendance.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-date')

        # Apply filters
        month = request.query_params.get('month')
        year = request.query_params.get('year')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if month and year:
            attendance_records = attendance_records.filter(date__month=month, date__year=year)
        if start_date:
            attendance_records = attendance_records.filter(date__gte=start_date)
        if end_date:
            attendance_records = attendance_records.filter(date__lte=end_date)

        # Summary
        total_records = attendance_records.count()
        present = attendance_records.filter(status='Present').count()
        absent = attendance_records.filter(status='Absent').count()
        late = attendance_records.filter(status='Late').count()
        half_day = attendance_records.filter(status='Half-Day').count()

        attendance_percentage = round(((present + late) / total_records) * 100, 2) if total_records > 0 else 0

        return Response({
            "child": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}"
            },
            "summary": {
                "total_days": total_records,
                "present": present,
                "absent": absent,
                "late": late,
                "half_day": half_day,
                "attendance_percentage": attendance_percentage,
                "status": "Excellent" if attendance_percentage >= 90 else "Good" if attendance_percentage >= 75 else "Needs Attention"
            },
            "records": [
                {
                    "date": record.date,
                    "status": record.status,
                    "remarks": record.remarks
                }
                for record in attendance_records[:50]  # Limit to 50 recent records
            ]
        })


class ParentChildGradeReportAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/{id}/grades/
    Returns complete grade report for a specific child
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

        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=child_id,
                school=request.user.school
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to view this child's data."},
                status=status.HTTP_403_FORBIDDEN
            )

        student = mapping.student
        
        # Get all grades
        grades = StudentGrade.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('exam', 'subject').order_by('-exam__start_date', 'subject__name')

        # Group by exam
        exam_groups = {}
        for grade in grades:
            exam_name = grade.exam.name
            if exam_name not in exam_groups:
                exam_groups[exam_name] = {
                    "exam_id": str(grade.exam.id),
                    "exam_name": exam_name,
                    "exam_date": grade.exam.start_date,
                    "is_published": grade.exam.is_published,
                    "subjects": []
                }
            
            exam_groups[exam_name]["subjects"].append({
                "subject_id": str(grade.subject.id),
                "subject_name": grade.subject.name,
                "marks_obtained": float(grade.marks_obtained),
                "max_marks": float(grade.max_marks),
                "percentage": round((grade.marks_obtained / grade.max_marks) * 100, 2) if grade.max_marks > 0 else 0,
                "remarks": grade.remarks
            })

        # Overall summary
        total_marks = sum(g.marks_obtained for g in grades)
        total_max = sum(g.max_marks for g in grades)
        overall_percentage = round((total_marks / total_max) * 100, 2) if total_max > 0 else 0

        return Response({
            "child": {
                "id": str(student.id),
                "name": f"{student.user.first_name} {student.user.last_name}",
                "enrollment_number": student.enrollment_number
            },
            "summary": {
                "total_subjects": grades.count(),
                "overall_percentage": overall_percentage,
                "total_exams": len(exam_groups)
            },
            "exams": list(exam_groups.values())
        })


class ParentSwitchChildAPIView(APIView):
    """
    POST /api/v1/profiles/parents/me/children/switch/
    Switch active child context for parent
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        child_id = request.data.get('child_id')
        
        if not child_id:
            return Response(
                {"detail": "child_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        # Verify child belongs to parent
        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=child_id,
                school=request.user.school
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "You are not authorized to access this child."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Store active child in session or create a user preference
        request.session['active_child_id'] = str(child_id)

        return Response({
            "detail": "Active child switched successfully.",
            "active_child": {
                "id": str(mapping.student.id),
                "name": f"{mapping.student.user.first_name} {mapping.student.user.last_name}",
                "relationship": mapping.relationship
            }
        })


class ParentActiveChildAPIView(APIView):
    """
    GET /api/v1/profiles/parents/me/children/active/
    Get currently active child
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        active_child_id = request.session.get('active_child_id')
        
        if not active_child_id:
            # Get first child as default
            first_mapping = ParentStudentMapping.objects.filter(
                parent=parent,
                school=request.user.school
            ).first()
            
            if first_mapping:
                active_child_id = str(first_mapping.student.id)
                request.session['active_child_id'] = active_child_id
            else:
                return Response(
                    {"detail": "No children found."},
                    status=status.HTTP_404_NOT_FOUND
                )

        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=active_child_id,
                school=request.user.school
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {"detail": "Active child not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response({
            "active_child": {
                "id": str(mapping.student.id),
                "name": f"{mapping.student.user.first_name} {mapping.student.user.last_name}",
                "email": mapping.student.user.email,
                "enrollment_number": mapping.student.enrollment_number,
                "relationship": mapping.relationship,
                "is_primary_contact": mapping.is_primary_contact
            }
        })