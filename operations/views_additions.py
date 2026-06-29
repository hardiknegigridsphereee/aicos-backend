# operations/views_additions.py
# Add these methods to the existing ViewSets in operations/views.py

# ============================================
# 1. Add to StudentSubmissionViewSet
# ============================================

@action(detail=False, methods=['get'], url_path='me')
def my_submissions(self, request):
    """
    GET /api/v1/operations/submissions/me/
    
    For Students: Returns their own submissions
    For Parents: Returns their child's submissions (requires ?student=ID)
    """
    user = request.user
    student_id = None
    
    # Check if user is a student
    try:
        student = StudentProfile.objects.get(user=user, school=user.school)
        student_id = student.id
    except StudentProfile.DoesNotExist:
        # Check if user is a parent
        try:
            parent = ParentProfile.objects.get(user=user, school=user.school)
            requested_student_id = request.query_params.get('student')
            if not requested_student_id:
                return Response(
                    {"detail": "student parameter is required for parent accounts."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            from profiles.models import ParentStudentMapping
            if not ParentStudentMapping.objects.filter(
                parent=parent, 
                student_id=requested_student_id,
                can_view_academics=True
            ).exists():
                return Response(
                    {"detail": "You are not authorized to view this student's data."},
                    status=status.HTTP_403_FORBIDDEN
                )
            student_id = requested_student_id
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Student or Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

    if not student_id:
        return Response(
            {"detail": "Student ID not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    submissions = StudentSubmission.objects.filter(
        student_id=student_id,
        school=request.user.school
    ).select_related('assignment', 'assignment__subject', 'assignment__section')\
     .order_by('-submitted_at')

    serializer = self.get_serializer(submissions, many=True)
    return Response({
        "count": submissions.count(),
        "results": serializer.data
    })


# ============================================
# 2. Add to TeacherAssignmentViewSet in academics/views.py
# ============================================

@action(detail=False, methods=['get'], url_path='me')
def my_assignments(self, request):
    """
    GET /api/v1/academics/teacher-assignments/me/
    Returns all teaching assignments for the current teacher
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        school=request.user.school
    ).select_related('academic_year', 'class_level', 'section', 'subject')

    # Filter by academic year
    academic_year_id = request.query_params.get('academic_year_id')
    if academic_year_id:
        assignments = assignments.filter(academic_year_id=academic_year_id)

    # Filter by status (current/historical)
    status_param = request.query_params.get('status')
    today = timezone.now().date()
    if status_param == 'current':
        assignments = assignments.filter(
            academic_year__start_date__lte=today,
            academic_year__end_date__gte=today
        )
    elif status_param == 'historical':
        assignments = assignments.filter(academic_year__end_date__lt=today)

    data = []
    for assignment in assignments:
        student_count = StudentEnrollment.objects.filter(
            school=request.user.school,
            section=assignment.section,
            academic_year=assignment.academic_year
        ).count()

        data.append({
            "id": str(assignment.id),
            "academic_year": {
                "id": str(assignment.academic_year.id),
                "name": assignment.academic_year.name
            },
            "class_level": {
                "id": str(assignment.class_level.id),
                "name": assignment.class_level.name
            },
            "section": {
                "id": str(assignment.section.id),
                "name": assignment.section.name
            },
            "subject": {
                "id": str(assignment.subject.id),
                "name": assignment.subject.name,
                "code": assignment.subject.code
            },
            "is_class_teacher": assignment.is_class_teacher,
            "student_count": student_count
        })

    return Response({
        "count": len(data),
        "results": data
    })


# ============================================
# 3. Add to AttendanceViewSet in operations/views.py
# ============================================

@action(detail=False, methods=['get'], url_path='me/today')
def my_today_attendance(self, request):
    """
    GET /api/v1/operations/attendance/me/today/
    Returns today's attendance for all sections the teacher teaches
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    today = timezone.now().date()
    
    # Get all sections this teacher teaches
    assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        school=request.user.school
    ).select_related('section', 'class_level', 'subject')

    sections_data = []
    for assignment in assignments:
        # Get students in this section
        enrollments = StudentEnrollment.objects.filter(
            school=request.user.school,
            section=assignment.section,
            academic_year=assignment.academic_year
        ).select_related('student__user')

        # Get today's attendance for these students
        student_ids = [e.student.id for e in enrollments]
        attendance_records = Attendance.objects.filter(
            school=request.user.school,
            section=assignment.section,
            date=today,
            student_id__in=student_ids
        ).select_related('student__user')

        # Build attendance data
        attendance_data = []
        for enrollment in enrollments:
            record = attendance_records.filter(student=enrollment.student).first()
            attendance_data.append({
                "student_id": str(enrollment.student.id),
                "student_name": f"{enrollment.student.user.first_name} {enrollment.student.user.last_name}",
                "roll_number": enrollment.roll_number,
                "status": record.status if record else "Not Marked",
                "remarks": record.remarks if record else ""
            })

        sections_data.append({
            "section_id": str(assignment.section.id),
            "section_name": assignment.section.name,
            "class_level": assignment.class_level.name,
            "subject": assignment.subject.name,
            "total_students": len(attendance_data),
            "marked": attendance_records.count(),
            "pending": len(attendance_data) - attendance_records.count(),
            "attendance": attendance_data
        })

    return Response({
        "date": today,
        "sections": sections_data
    })


@action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)')
def my_section_attendance(self, request, section_id):
    """
    GET /api/v1/operations/attendance/me/section/{section_id}/
    Returns attendance for a specific section
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Verify teacher is assigned to this section
    assignment = TeacherAssignment.objects.filter(
        teacher=teacher,
        section_id=section_id,
        school=request.user.school
    ).first()

    if not assignment:
        return Response(
            {"detail": "You are not assigned to this section."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get date range
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    month = request.query_params.get('month')
    year = request.query_params.get('year')

    # Get attendance records for this section
    attendance_qs = Attendance.objects.filter(
        school=request.user.school,
        section_id=section_id
    ).select_related('student__user')

    if start_date:
        attendance_qs = attendance_qs.filter(date__gte=start_date)
    if end_date:
        attendance_qs = attendance_qs.filter(date__lte=end_date)
    if month and year:
        attendance_qs = attendance_qs.filter(date__month=month, date__year=year)

    # Group by date
    dates_data = {}
    for record in attendance_qs:
        date_str = record.date.isoformat()
        if date_str not in dates_data:
            dates_data[date_str] = {
                "date": date_str,
                "total": 0,
                "present": 0,
                "absent": 0,
                "late": 0,
                "half_day": 0,
                "records": []
            }
        dates_data[date_str]["total"] += 1
        status_key = record.status.lower()
        if status_key in dates_data[date_str]:
            dates_data[date_str][status_key] += 1
        dates_data[date_str]["records"].append({
            "student_id": str(record.student.id),
            "student_name": record.student.user.first_name,
            "status": record.status,
            "remarks": record.remarks
        })

    return Response({
        "section": {
            "id": str(assignment.section.id),
            "name": assignment.section.name,
            "class_level": assignment.class_level.name,
            "subject": assignment.subject.name
        },
        "attendance": list(dates_data.values())
    })


@action(detail=False, methods=['get'], url_path='me/summary')
def my_attendance_summary(self, request):
    """
    GET /api/v1/operations/attendance/me/summary/
    Returns attendance summary across all sections the teacher teaches
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get all sections this teacher teaches
    assignments = TeacherAssignment.objects.filter(
        teacher=teacher,
        school=request.user.school
    ).select_related('section', 'class_level', 'subject', 'academic_year')

    summary_data = []
    total_students = 0
    total_present = 0

    for assignment in assignments:
        # Get students in this section
        enrollments = StudentEnrollment.objects.filter(
            school=request.user.school,
            section=assignment.section,
            academic_year=assignment.academic_year
        )

        student_count = enrollments.count()
        total_students += student_count

        # Get attendance for this section
        today = timezone.now().date()
        thirty_days_ago = today - timedelta(days=30)
        
        attendance_records = Attendance.objects.filter(
            school=request.user.school,
            section=assignment.section,
            date__gte=thirty_days_ago
        )

        present_count = attendance_records.filter(status__in=['Present', 'Late']).count()
        total_present += present_count
        
        attendance_percentage = round((present_count / (student_count * 30)) * 100, 2) if student_count > 0 else 0

        summary_data.append({
            "section_id": str(assignment.section.id),
            "section_name": assignment.section.name,
            "class_level": assignment.class_level.name,
            "subject": assignment.subject.name,
            "student_count": student_count,
            "last_30_days": {
                "total_records": attendance_records.count(),
                "present": attendance_records.filter(status='Present').count(),
                "absent": attendance_records.filter(status='Absent').count(),
                "late": attendance_records.filter(status='Late').count(),
                "half_day": attendance_records.filter(status='Half-Day').count(),
                "attendance_percentage": attendance_percentage
            }
        })

    overall_percentage = round((total_present / (total_students * 30)) * 100, 2) if total_students > 0 else 0

    return Response({
        "summary": {
            "total_sections": len(summary_data),
            "total_students": total_students,
            "overall_attendance_percentage": overall_percentage
        },
        "sections": summary_data
    })


# ============================================
# 4. Add to StudentGradeViewSet in operations/views.py
# ============================================

@action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)/exam/(?P<exam_id>[^/.]+)')
def my_section_gradebook(self, request, section_id, exam_id):
    """
    GET /api/v1/operations/grades/me/section/{section_id}/exam/{exam_id}/
    Returns gradebook for a specific section and exam
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Verify teacher is assigned to this section
    assignment = TeacherAssignment.objects.filter(
        teacher=teacher,
        section_id=section_id,
        school=request.user.school
    ).first()

    if not assignment:
        return Response(
            {"detail": "You are not assigned to this section."},
            status=status.HTTP_403_FORBIDDEN
        )

    # Get exam
    try:
        exam = Exam.objects.get(id=exam_id, school=request.user.school)
    except Exam.DoesNotExist:
        return Response(
            {"detail": "Exam not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get students in this section
    enrollments = StudentEnrollment.objects.filter(
        school=request.user.school,
        section_id=section_id,
        academic_year=exam.academic_year
    ).select_related('student__user')

    # Get grades for these students
    student_ids = [e.student.id for e in enrollments]
    grades = StudentGrade.objects.filter(
        school=request.user.school,
        exam_id=exam_id,
        student_id__in=student_ids,
        subject=assignment.subject
    ).select_related('student__user')

    # Build gradebook
    gradebook = []
    for enrollment in enrollments:
        student = enrollment.student
        grade = grades.filter(student=student).first()
        gradebook.append({
            "student_id": str(student.id),
            "student_name": f"{student.user.first_name} {student.user.last_name}",
            "roll_number": enrollment.roll_number,
            "marks_obtained": float(grade.marks_obtained) if grade else None,
            "max_marks": float(grade.max_marks) if grade else 100.00,
            "percentage": float(grade.marks_obtained / grade.max_marks * 100) if grade and grade.max_marks > 0 else None,
            "remarks": grade.remarks if grade else None,
            "graded": bool(grade)
        })

    # Statistics
    graded = [g for g in gradebook if g['graded']]
    total_marks = sum(g['marks_obtained'] for g in graded if g['marks_obtained'])
    total_max = sum(g['max_marks'] for g in graded if g['max_marks'])
    avg_percentage = round((total_marks / total_max) * 100, 2) if total_max > 0 else 0

    return Response({
        "exam": {
            "id": str(exam.id),
            "name": exam.name,
            "date": exam.start_date
        },
        "subject": {
            "id": str(assignment.subject.id),
            "name": assignment.subject.name
        },
        "section": {
            "id": str(assignment.section.id),
            "name": assignment.section.name,
            "class_level": assignment.class_level.name
        },
        "summary": {
            "total_students": len(gradebook),
            "graded_students": len(graded),
            "average_percentage": avg_percentage,
            "highest": max((g['percentage'] for g in graded if g['percentage']), default=0),
            "lowest": min((g['percentage'] for g in graded if g['percentage']), default=0)
        },
        "gradebook": gradebook
    })


# ============================================
# 5. Add to AssignmentViewSet in operations/views.py
# ============================================

@action(detail=False, methods=['get'], url_path='me')
def my_assignments(self, request):
    """
    GET /api/v1/operations/assignments/me/
    Returns assignments created by the current teacher
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    assignments = Assignment.objects.filter(
        teacher=teacher,
        school=request.user.school
    ).select_related('subject', 'section').order_by('-created_at')

    # Filter by section
    section_id = request.query_params.get('section_id')
    if section_id:
        assignments = assignments.filter(section_id=section_id)

    # Filter by subject
    subject_id = request.query_params.get('subject_id')
    if subject_id:
        assignments = assignments.filter(subject_id=subject_id)

    # Filter by status (upcoming/past)
    status_filter = request.query_params.get('status')
    now = timezone.now()
    if status_filter == 'upcoming':
        assignments = assignments.filter(due_date__gte=now)
    elif status_filter == 'past':
        assignments = assignments.filter(due_date__lt=now)

    data = []
    for assignment in assignments:
        submission_count = StudentSubmission.objects.filter(
            assignment=assignment
        ).count()
        
        graded_count = StudentSubmission.objects.filter(
            assignment=assignment,
            grade__isnull=False
        ).count()

        data.append({
            "id": str(assignment.id),
            "title": assignment.title,
            "description": assignment.description,
            "subject": {
                "id": str(assignment.subject.id),
                "name": assignment.subject.name
            },
            "section": {
                "id": str(assignment.section.id),
                "name": assignment.section.name
            },
            "due_date": assignment.due_date,
            "created_at": assignment.created_at,
            "submission_count": submission_count,
            "graded_count": graded_count,
            "pending_grading": submission_count - graded_count
        })

    return Response({
        "count": len(data),
        "results": data
    })


# ============================================
# 6. Add to StudentSubmissionViewSet in operations/views.py
# ============================================

@action(detail=False, methods=['get'], url_path='me/pending')
def my_pending_submissions(self, request):
    """
    GET /api/v1/operations/submissions/me/pending/
    Returns submissions pending grading for the teacher
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Get all assignments created by this teacher
    assignments = Assignment.objects.filter(
        teacher=teacher,
        school=request.user.school
    )

    # Get pending submissions
    pending_submissions = StudentSubmission.objects.filter(
        school=request.user.school,
        assignment__in=assignments,
        grade__isnull=True,
        status='Submitted'
    ).select_related('assignment', 'student__user', 'assignment__subject', 'assignment__section')

    # Filter by assignment if provided
    assignment_id = request.query_params.get('assignment_id')
    if assignment_id:
        pending_submissions = pending_submissions.filter(assignment_id=assignment_id)

    data = []
    for submission in pending_submissions:
        data.append({
            "id": str(submission.id),
            "student": {
                "id": str(submission.student.id),
                "name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                "enrollment_number": submission.student.enrollment_number
            },
            "assignment": {
                "id": str(submission.assignment.id),
                "title": submission.assignment.title,
                "subject": submission.assignment.subject.name,
                "section": submission.assignment.section.name,
                "due_date": submission.assignment.due_date
            },
            "submitted_at": submission.submitted_at,
            "file": submission.file.url if submission.file else None
        })

    return Response({
        "count": len(data),
        "results": data
    })


@action(detail=False, methods=['get'], url_path='me/assignment/(?P<assignment_id>[^/.]+)')
def my_assignment_submissions(self, request, assignment_id):
    """
    GET /api/v1/operations/submissions/me/assignment/{assignment_id}/
    Returns all submissions for a specific assignment
    """
    try:
        teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
    except TeacherProfile.DoesNotExist:
        return Response(
            {"detail": "Teacher profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    # Verify teacher owns this assignment
    assignment = Assignment.objects.filter(
        id=assignment_id,
        teacher=teacher,
        school=request.user.school
    ).first()

    if not assignment:
        return Response(
            {"detail": "Assignment not found or you don't have permission."},
            status=status.HTTP_403_FORBIDDEN
        )

    submissions = StudentSubmission.objects.filter(
        assignment=assignment,
        school=request.user.school
    ).select_related('student__user').order_by('-submitted_at')

    data = []
    for submission in submissions:
        data.append({
            "id": str(submission.id),
            "student": {
                "id": str(submission.student.id),
                "name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                "enrollment_number": submission.student.enrollment_number
            },
            "file": submission.file.url if submission.file else None,
            "submitted_at": submission.submitted_at,
            "grade": float(submission.grade) if submission.grade is not None else None,
            "status": submission.status,
            "remarks": getattr(submission, 'remarks', '')
        })

    # Statistics
    total = len(data)
    graded = len([s for s in data if s['grade'] is not None])
    pending = total - graded

    return Response({
        "assignment": {
            "id": str(assignment.id),
            "title": assignment.title,
            "description": assignment.description,
            "subject": assignment.subject.name,
            "section": assignment.section.name,
            "due_date": assignment.due_date
        },
        "summary": {
            "total_submissions": total,
            "graded": graded,
            "pending": pending
        },
        "submissions": data
    })