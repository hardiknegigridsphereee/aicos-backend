from django.db import transaction
from django.utils import timezone
from datetime import datetime
from core.utils.r2_storage import r2_storage
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema
import uuid
import os

from tenants.views import TenantAwareModelViewSet
from profiles.models import StudentProfile, ParentProfile, TeacherProfile
from academics.models import StudentEnrollment, TeacherAssignment
from accounts.permissions import IsStudent, IsTeacher, IsTeacherOrStaff
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from .serializers import (
    AttendanceSerializer, BulkAttendanceSerializer,
    ExamSerializer, StudentGradeSerializer, BulkGradeSubmitSerializer,
    AssignmentSerializer, AssignmentWithStatusSerializer,
    StudentSubmissionSerializer, SubmissionWithViewUrlSerializer,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _file_path_str(file_field):
    """Safely convert a FileField / string / None to a plain string path."""
    if not file_field:
        return None
    return str(file_field.name) if hasattr(file_field, 'name') else str(file_field)


def _embed_view_url(file_field, expires_in=604800):
    """Generate a 7-day inline view URL for a submission file. Returns None on failure."""
    path = _file_path_str(file_field)
    if not path:
        return None
    try:
        return r2_storage.generate_view_url(path, expires_in=expires_in)['url']
    except Exception:
        return None


def _attach_view_urls(submissions):
    """
    Attach _view_url to each submission object in-place.
    Call this before passing to SubmissionWithViewUrlSerializer.
    """
    for s in submissions:
        s._view_url = _embed_view_url(s.file)
    return submissions


def get_caller_student_id(user):
    profile = StudentProfile.objects.filter(user=user).first()
    return profile.id if profile else None


def parent_can_access_student(user, student_id, require_academics=True):
    parent_profile = ParentProfile.objects.filter(user=user).first()
    if not parent_profile:
        return False
    from profiles.models import ParentStudentMapping
    qs = ParentStudentMapping.objects.filter(parent=parent_profile, student_id=student_id)
    if require_academics:
        qs = qs.filter(can_view_academics=True)
    return qs.exists()


def resolve_effective_student_id(request):
    user = request.user
    requested = request.query_params.get('student')
    own = get_caller_student_id(user)
    if own:
        return str(own)
    parent = ParentProfile.objects.filter(user=user).first()
    if parent:
        if not requested:
            raise ValidationError({"student": "Required for parent accounts."})
        if not parent_can_access_student(user, requested):
            raise PermissionDenied("Not authorized to view this student's data.")
        return requested
    return requested


# ---------------------------------------------------------------------------
# ATTENDANCE
# ---------------------------------------------------------------------------

class AttendanceViewSet(TenantAwareModelViewSet):
    queryset = Attendance.objects.select_related(
        'student__user', 'academic_year', 'class_level', 'section'
    ).all()
    serializer_class = AttendanceSerializer

    def get_permissions(self):
        if self.action in ['my_attendance', 'my_attendance_summary']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                return qs.filter(student=student)
            except StudentProfile.DoesNotExist:
                pass
        for param, field in [('date', 'date'), ('student', 'student_id'), ('section', 'section_id')]:
            v = self.request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        return qs

    @extend_schema(request=BulkAttendanceSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-record')
    def bulk_record(self, request):
        serializer = BulkAttendanceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school
        objects = [
            Attendance(
                school=school,
                academic_year_id=data['academic_year_id'],
                class_level_id=data['class_level_id'],
                section_id=data['section_id'],
                date=data['date'],
                student_id=r['student_id'],
                status=r['status'],
                remarks=r.get('remarks', '')
            ) for r in data['records']
        ]
        with transaction.atomic():
            Attendance.objects.bulk_create(
                objects, update_conflicts=True,
                unique_fields=['school', 'student', 'date'],
                update_fields=['status', 'remarks']
            )
        return Response({"detail": f"Processed {len(objects)} records."})

    @action(detail=False, methods=['get'], url_path='me')
    def my_attendance(self, request):
        user = request.user
        student_id = None
        try:
            student_id = StudentProfile.objects.get(user=user, school=user.school).id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                sid = request.query_params.get('student')
                if not sid:
                    return Response({"detail": "student param required for parents."}, status=400)
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(parent=parent, student_id=sid, can_view_academics=True).exists():
                    return Response({"detail": "Not authorized."}, status=403)
                student_id = sid
            except ParentProfile.DoesNotExist:
                pass

        qs = Attendance.objects.filter(school=request.user.school)
        if student_id:
            qs = qs.filter(student_id=student_id)
        for param, field in [
            ('start_date', 'date__gte'), ('end_date', 'date__lte'),
            ('month', 'date__month'), ('year', 'date__year'),
        ]:
            v = request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        qs = qs.order_by('-date')
        serializer = self.get_serializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})

    @action(detail=False, methods=['get'], url_path='me/summary')
    def my_attendance_summary(self, request):
        user = request.user
        student_id = None
        try:
            student_id = StudentProfile.objects.get(user=user, school=user.school).id
        except StudentProfile.DoesNotExist:
            try:
                parent = ParentProfile.objects.get(user=user, school=user.school)
                sid = request.query_params.get('student')
                if not sid:
                    return Response({"detail": "student param required for parents."}, status=400)
                from profiles.models import ParentStudentMapping
                if not ParentStudentMapping.objects.filter(parent=parent, student_id=sid, can_view_academics=True).exists():
                    return Response({"detail": "Not authorized."}, status=403)
                student_id = sid
            except ParentProfile.DoesNotExist:
                pass

        qs = Attendance.objects.filter(school=request.user.school)
        if student_id:
            qs = qs.filter(student_id=student_id)
        for param, field in [('academic_year_id', 'academic_year_id'), ('month', 'date__month'), ('year', 'date__year')]:
            v = request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})

        total = qs.count()
        if total == 0:
            return Response({"total_days": 0, "present": 0, "absent": 0, "late": 0,
                             "half_day": 0, "attendance_percentage": 0, "status": "No records"})
        present = qs.filter(status='Present').count()
        absent = qs.filter(status='Absent').count()
        late = qs.filter(status='Late').count()
        half_day = qs.filter(status='Half-Day').count()
        pct = round(((present + late) / total) * 100, 2)
        return Response({
            "total_days": total, "present": present, "absent": absent,
            "late": late, "half_day": half_day, "attendance_percentage": pct,
            "status": "Excellent" if pct >= 90 else "Good" if pct >= 75 else "Needs Improvement"
        })

    @action(detail=False, methods=['get'], url_path='me/today')
    def my_today_attendance(self, request):
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)
        today = timezone.now().date()
        assignments = TeacherAssignment.objects.filter(
            teacher=teacher, school=request.user.school
        ).select_related('section', 'class_level', 'subject', 'academic_year')
        sections_data = []
        for a in assignments:
            enrollments = StudentEnrollment.objects.filter(
                school=request.user.school, section=a.section, academic_year=a.academic_year
            ).select_related('student__user')
            student_ids = [e.student.id for e in enrollments]
            records = Attendance.objects.filter(
                school=request.user.school, section=a.section, date=today, student_id__in=student_ids
            )
            attendance_data = []
            for e in enrollments:
                rec = records.filter(student=e.student).first()
                attendance_data.append({
                    "student_id": str(e.student.id),
                    "student_name": f"{e.student.user.first_name} {e.student.user.last_name}",
                    "roll_number": e.roll_number,
                    "status": rec.status if rec else "Not Marked",
                    "remarks": rec.remarks if rec else ""
                })
            sections_data.append({
                "section_id": str(a.section.id), "section_name": a.section.name,
                "class_level": a.class_level.name, "subject": a.subject.name,
                "total_students": len(attendance_data),
                "marked": records.count(), "pending": len(attendance_data) - records.count(),
                "attendance": attendance_data
            })
        return Response({"date": today.isoformat(), "sections": sections_data})

    @action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)')
    def my_section_attendance(self, request, section_id):
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)
        a = TeacherAssignment.objects.filter(teacher=teacher, section_id=section_id, school=request.user.school).first()
        if not a:
            return Response({"detail": "Not assigned to this section."}, status=403)
        qs = Attendance.objects.filter(school=request.user.school, section_id=section_id).select_related('student__user')
        for param, field in [('start_date', 'date__gte'), ('end_date', 'date__lte'), ('month', 'date__month'), ('year', 'date__year')]:
            v = request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        dates_data = {}
        for rec in qs:
            ds = rec.date.isoformat()
            if ds not in dates_data:
                dates_data[ds] = {"date": ds, "total": 0, "present": 0, "absent": 0, "late": 0, "half_day": 0, "records": []}
            dates_data[ds]["total"] += 1
            sk = rec.status.lower().replace('-', '_')
            if sk in dates_data[ds]:
                dates_data[ds][sk] += 1
            dates_data[ds]["records"].append({
                "student_id": str(rec.student.id),
                "student_name": rec.student.user.first_name,
                "status": rec.status, "remarks": rec.remarks
            })
        return Response({
            "section": {"id": str(a.section.id), "name": a.section.name,
                        "class_level": a.class_level.name, "subject": a.subject.name},
            "attendance": list(dates_data.values())
        })


# ---------------------------------------------------------------------------
# EXAM
# ---------------------------------------------------------------------------

class ExamViewSet(TenantAwareModelViewSet):
    queryset = Exam.objects.select_related('academic_year').all()
    serializer_class = ExamSerializer

    def get_permissions(self):
        if self.action in ['my_exams', 'my_upcoming_exams']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                enrollment = StudentEnrollment.objects.filter(
                    student=student, school=user.school
                ).order_by('-academic_year__start_date').first()
                return qs.filter(academic_year=enrollment.academic_year) if enrollment else qs.none()
            except StudentProfile.DoesNotExist:
                pass
        return qs

    def _resolve_student(self, request):
        user = request.user
        try:
            return StudentProfile.objects.get(user=user, school=user.school)
        except StudentProfile.DoesNotExist:
            pass
        try:
            parent = ParentProfile.objects.get(user=user, school=user.school)
            sid = request.query_params.get('student')
            if not sid:
                return Response({"detail": "student param required for parents."}, status=400)
            from profiles.models import ParentStudentMapping
            if not ParentStudentMapping.objects.filter(parent=parent, student_id=sid, can_view_academics=True).exists():
                return Response({"detail": "Not authorized."}, status=403)
            return StudentProfile.objects.get(id=sid, school=request.user.school)
        except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
            return Response({"detail": "Student not found."}, status=404)

    @action(detail=False, methods=['get'], url_path='me')
    def my_exams(self, request):
        student = self._resolve_student(request)
        if isinstance(student, Response):
            return student
        enrollment = StudentEnrollment.objects.filter(student=student, school=request.user.school).order_by('-academic_year__start_date').first()
        if not enrollment:
            return Response({"count": 0, "results": []})
        exams = Exam.objects.filter(school=request.user.school, academic_year=enrollment.academic_year).order_by('start_date')
        return Response({"count": exams.count(), "results": self.get_serializer(exams, many=True).data})

    @action(detail=False, methods=['get'], url_path='me/upcoming')
    def my_upcoming_exams(self, request):
        student = self._resolve_student(request)
        if isinstance(student, Response):
            return student
        enrollment = StudentEnrollment.objects.filter(student=student, school=request.user.school).order_by('-academic_year__start_date').first()
        if not enrollment:
            return Response({"count": 0, "results": []})
        today = timezone.now().date()
        exams = Exam.objects.filter(
            school=request.user.school, academic_year=enrollment.academic_year, start_date__gte=today
        ).order_by('start_date')
        return Response({"count": exams.count(), "results": self.get_serializer(exams, many=True).data})


# ---------------------------------------------------------------------------
# GRADES
# ---------------------------------------------------------------------------

class StudentGradeViewSet(TenantAwareModelViewSet):
    queryset = StudentGrade.objects.select_related('student__user', 'exam', 'subject').all()
    serializer_class = StudentGradeSerializer

    def get_permissions(self):
        if self.action in ['my_grades', 'my_report_card', 'my_section_gradebook']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                return qs.filter(student=StudentProfile.objects.get(user=user))
            except StudentProfile.DoesNotExist:
                pass
        for param, field in [('exam', 'exam_id'), ('student', 'student_id'), ('subject', 'subject_id')]:
            v = self.request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        return qs

    @extend_schema(request=BulkGradeSubmitSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-submit')
    def bulk_submit(self, request):
        serializer = BulkGradeSubmitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school
        objects = [
            StudentGrade(
                school=school, exam_id=data['exam_id'], subject_id=data['subject_id'],
                student_id=r['student_id'], marks_obtained=r['marks_obtained'],
                max_marks=r.get('max_marks', 100.00), remarks=r.get('remarks', '')
            ) for r in data['records']
        ]
        with transaction.atomic():
            StudentGrade.objects.bulk_create(
                objects, update_conflicts=True,
                unique_fields=['school', 'exam', 'student', 'subject'],
                update_fields=['marks_obtained', 'max_marks', 'remarks']
            )
        return Response({"detail": f"Processed grades for {len(objects)} students."})

    def _resolve_student_id(self, request):
        user = request.user
        try:
            return StudentProfile.objects.get(user=user, school=user.school).id
        except StudentProfile.DoesNotExist:
            pass
        try:
            parent = ParentProfile.objects.get(user=user, school=user.school)
            sid = request.query_params.get('student')
            if not sid:
                return Response({"detail": "student param required for parents."}, status=400)
            from profiles.models import ParentStudentMapping
            if not ParentStudentMapping.objects.filter(parent=parent, student_id=sid, can_view_academics=True).exists():
                return Response({"detail": "Not authorized."}, status=403)
            return sid
        except ParentProfile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=404)

    @action(detail=False, methods=['get'], url_path='me')
    def my_grades(self, request):
        student_id = self._resolve_student_id(request)
        if isinstance(student_id, Response):
            return student_id
        qs = StudentGrade.objects.filter(
            student_id=student_id, school=request.user.school
        ).select_related('exam', 'subject', 'exam__academic_year')
        if request.query_params.get('exam_id'):
            qs = qs.filter(exam_id=request.query_params['exam_id'])
        if request.query_params.get('academic_year_id'):
            qs = qs.filter(exam__academic_year_id=request.query_params['academic_year_id'])
        qs = qs.order_by('-exam__start_date', 'subject__name')
        return Response({"count": qs.count(), "results": self.get_serializer(qs, many=True).data})

    @action(detail=False, methods=['get'], url_path='me/report-card')
    def my_report_card(self, request):
        student_id = self._resolve_student_id(request)
        if isinstance(student_id, Response):
            return student_id
        try:
            student = StudentProfile.objects.get(id=student_id, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student not found."}, status=404)
        qs = StudentGrade.objects.filter(
            student=student, school=request.user.school
        ).select_related('exam', 'subject', 'exam__academic_year')
        if request.query_params.get('academic_year_id'):
            qs = qs.filter(exam__academic_year_id=request.query_params['academic_year_id'])
        exams_data = {}
        for g in qs:
            en = g.exam.name
            if en not in exams_data:
                exams_data[en] = {"exam_id": str(g.exam.id), "exam_name": en,
                                  "exam_date": g.exam.start_date, "is_published": g.exam.is_published, "subjects": []}
            exams_data[en]["subjects"].append({
                "subject_id": str(g.subject.id), "subject_name": g.subject.name,
                "marks_obtained": float(g.marks_obtained), "max_marks": float(g.max_marks),
                "percentage": round(float(g.marks_obtained / g.max_marks * 100), 2) if g.max_marks > 0 else 0,
                "remarks": g.remarks
            })
        all_grades = list(qs)
        total_marks = sum(g.marks_obtained for g in all_grades)
        total_max = sum(g.max_marks for g in all_grades)
        overall = round(float(total_marks / total_max * 100), 2) if total_max > 0 else 0
        return Response({
            "student_name": f"{student.user.first_name} {student.user.last_name}",
            "enrollment_number": student.enrollment_number,
            "overall_percentage": overall,
            "total_subjects": len(all_grades),
            "exams": list(exams_data.values())
        })

    @action(detail=False, methods=['get'], url_path='me/section/(?P<section_id>[^/.]+)/exam/(?P<exam_id>[^/.]+)')
    def my_section_gradebook(self, request, section_id, exam_id):
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)
        assignment = TeacherAssignment.objects.filter(teacher=teacher, section_id=section_id, school=request.user.school).first()
        if not assignment:
            return Response({"detail": "Not assigned to this section."}, status=403)
        try:
            exam = Exam.objects.get(id=exam_id, school=request.user.school)
        except Exam.DoesNotExist:
            return Response({"detail": "Exam not found."}, status=404)
        enrollments = StudentEnrollment.objects.filter(
            school=request.user.school, section_id=section_id, academic_year=exam.academic_year
        ).select_related('student__user')
        student_ids = [e.student.id for e in enrollments]
        grades = StudentGrade.objects.filter(
            school=request.user.school, exam_id=exam_id, student_id__in=student_ids, subject=assignment.subject
        )
        grade_map = {g.student_id: g for g in grades}
        gradebook = []
        for e in enrollments:
            g = grade_map.get(e.student.id)
            gradebook.append({
                "student_id": str(e.student.id),
                "student_name": f"{e.student.user.first_name} {e.student.user.last_name}",
                "roll_number": e.roll_number,
                "marks_obtained": float(g.marks_obtained) if g else None,
                "max_marks": float(g.max_marks) if g else 100.0,
                "percentage": round(float(g.marks_obtained / g.max_marks * 100), 2) if g and g.max_marks > 0 else None,
                "remarks": g.remarks if g else None,
                "graded": bool(g)
            })
        graded = [x for x in gradebook if x['graded']]
        tm = sum(x['marks_obtained'] for x in graded if x['marks_obtained'])
        tmx = sum(x['max_marks'] for x in graded if x['max_marks'])
        avg = round(tm / tmx * 100, 2) if tmx > 0 else 0
        return Response({
            "exam": {"id": str(exam.id), "name": exam.name, "date": exam.start_date},
            "subject": {"id": str(assignment.subject.id), "name": assignment.subject.name},
            "section": {"id": str(assignment.section.id), "name": assignment.section.name, "class_level": assignment.class_level.name},
            "summary": {"total_students": len(gradebook), "graded_students": len(graded), "average_percentage": avg,
                        "highest": max((x['percentage'] for x in graded if x['percentage']), default=0),
                        "lowest": min((x['percentage'] for x in graded if x['percentage']), default=0)},
            "gradebook": gradebook
        })


# ---------------------------------------------------------------------------
# ASSIGNMENT
# ---------------------------------------------------------------------------

class AssignmentViewSet(TenantAwareModelViewSet):
    queryset = Assignment.objects.select_related('subject', 'section', 'teacher').all()
    serializer_class = AssignmentSerializer

    def get_permissions(self):
        if self.action in ['for_student', 'my_assignments', 'my_upcoming_assignments']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        own_student_id = get_caller_student_id(self.request.user)
        if own_student_id:
            enrollment = StudentEnrollment.objects.filter(
                student_id=own_student_id
            ).order_by('-academic_year__start_date').first()
            return qs.filter(section_id=enrollment.section_id) if enrollment else qs.none()
        for param, field in [('section', 'section_id'), ('subject', 'subject_id'), ('teacher', 'teacher_id')]:
            v = self.request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        if not (user.is_superuser or user.is_staff or TeacherProfile.objects.filter(user=user).exists()):
            raise PermissionDenied("Only teachers can create assignments.")
        super().perform_create(serializer)

    @action(detail=False, methods=['get'], url_path='for-student')
    def for_student(self, request):
        sid = resolve_effective_student_id(request)
        if not sid:
            raise ValidationError({"student": "Required."})
        enrollment = StudentEnrollment.objects.filter(student_id=sid).order_by('-academic_year__start_date').first()
        if not enrollment:
            return Response({"count": 0, "results": []})
        assignments = Assignment.objects.filter(
            school=request.user.school, section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')
        serializer = AssignmentWithStatusSerializer(assignments, many=True, context={'student_id': sid})
        return Response({"count": assignments.count(), "results": serializer.data})

    @action(detail=False, methods=['get'], url_path='me')
    def my_assignments(self, request):
        """Student: list own assignments with submission status."""
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student profile not found."}, status=404)
        enrollment = StudentEnrollment.objects.filter(
            student=student, school=request.user.school
        ).order_by('-academic_year__start_date').first()
        if not enrollment:
            return Response({"count": 0, "results": []})
        assignments = Assignment.objects.filter(
            school=request.user.school, section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')
        serializer = AssignmentWithStatusSerializer(assignments, many=True, context={'student_id': str(student.id)})
        return Response({"count": assignments.count(), "results": serializer.data})

    @action(detail=False, methods=['get'], url_path='me/upcoming')
    def my_upcoming_assignments(self, request):
        """Student: upcoming assignments only."""
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student profile not found."}, status=404)
        enrollment = StudentEnrollment.objects.filter(
            student=student, school=request.user.school
        ).order_by('-academic_year__start_date').first()
        if not enrollment:
            return Response({"count": 0, "results": []})
        now = timezone.now()
        assignments = Assignment.objects.filter(
            school=request.user.school, section_id=enrollment.section_id, due_date__gte=now
        ).select_related('subject', 'section', 'teacher').order_by('due_date')
        serializer = AssignmentWithStatusSerializer(assignments, many=True, context={'student_id': str(student.id)})
        return Response({"count": assignments.count(), "results": serializer.data})

    @action(detail=False, methods=['get'], url_path='me/teacher')
    def my_teacher_assignments(self, request):
        """Teacher: list all their assignments with submission stats."""
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)
        assignments = Assignment.objects.filter(
            teacher=teacher, school=request.user.school
        ).select_related('subject', 'section').order_by('-created_at')
        if request.query_params.get('section_id'):
            assignments = assignments.filter(section_id=request.query_params['section_id'])
        if request.query_params.get('subject_id'):
            assignments = assignments.filter(subject_id=request.query_params['subject_id'])
        status_filter = request.query_params.get('status')
        now = timezone.now()
        if status_filter == 'upcoming':
            assignments = assignments.filter(due_date__gte=now)
        elif status_filter == 'past':
            assignments = assignments.filter(due_date__lt=now)
        data = []
        for a in assignments:
            total = StudentSubmission.objects.filter(assignment=a).count()
            graded = StudentSubmission.objects.filter(assignment=a, grade__isnull=False).count()
            data.append({
                "id": str(a.id), "title": a.title, "description": a.description,
                "subject": {"id": str(a.subject.id), "name": a.subject.name},
                "section": {"id": str(a.section.id), "name": a.section.name},
                "due_date": a.due_date, "created_at": a.created_at,
                "submission_count": total, "graded_count": graded, "pending_grading": total - graded
            })
        return Response({"count": len(data), "results": data})


# ---------------------------------------------------------------------------
# SUBMISSION  — simplified, mirrors profile picture pattern
# ---------------------------------------------------------------------------

class StudentSubmissionViewSet(TenantAwareModelViewSet):
    """
    STUDENT
    -------
    Step 1: POST /submissions/request-upload/
            Body: {assignment_id, file_name, content_type}
            → {upload_url, file_path, expires_in, assignment}
            (identical shape to profile picture upload URL response)

    Step 2: Frontend PUTs the file directly to upload_url (R2 signed URL).

    Step 3: POST /submissions/confirm/
            Body: {assignment_id, file_path}
            → full submission row with embedded view_url
            (identical to confirming a profile picture)

    GET /submissions/me/
        → all own submissions, each with embedded view_url

    TEACHER
    -------
    GET  /submissions/assignment/{id}/
         → all submissions for that assignment + view_url per row

    PATCH /submissions/{id}/grade/
          Body: {grade, remarks}
          → updated submission row + refreshed view_url

    GET  /submissions/pending/
         → all ungraded submissions across teacher's assignments
    """

    queryset = StudentSubmission.objects.select_related(
        'assignment__subject', 'assignment__section', 'student__user'
    ).all()
    serializer_class = StudentSubmissionSerializer

    def get_permissions(self):
        if self.action in ['request_upload', 'confirm', 'my_submissions']:
            return [IsAuthenticated(), IsStudent()]
        if self.action in ['assignment_submissions', 'grade_submission', 'pending_submissions']:
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated(), IsTeacher()]

    def get_queryset(self):
        qs = super().get_queryset()
        own = get_caller_student_id(self.request.user)
        if own:
            return qs.filter(student_id=own)
        parent = ParentProfile.objects.filter(user=self.request.user).first()
        if parent:
            sid = self.request.query_params.get('student')
            if not sid or not parent_can_access_student(self.request.user, sid):
                return qs.none()
            return qs.filter(student_id=sid)
        # teacher / staff — filter by query params
        for param, field in [('student', 'student_id'), ('assignment', 'assignment_id')]:
            v = self.request.query_params.get(param)
            if v:
                qs = qs.filter(**{field: v})
        return qs

    # ------------------------------------------------------------------
    # STEP 1 — student requests a signed upload URL (same as profile pic)
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='request-upload')
    def request_upload(self, request):
        """
        POST /api/v1/operations/submissions/request-upload/
        Body: { "assignment_id": "uuid", "file_name": "essay.pdf", "content_type": "application/pdf" }

        Returns a signed R2 PUT URL. The frontend uploads the file directly
        to that URL — the Django server never touches the bytes.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student profile not found."}, status=404)

        assignment_id = request.data.get('assignment_id')
        file_name = request.data.get('file_name', '')
        content_type = request.data.get('content_type', 'application/octet-stream')

        if not assignment_id:
            raise ValidationError({"assignment_id": "Required."})
        if not file_name:
            raise ValidationError({"file_name": "Required."})

        try:
            assignment = Assignment.objects.get(id=assignment_id, school=request.user.school)
        except Assignment.DoesNotExist:
            return Response({"detail": "Assignment not found."}, status=404)

        # Build an organised, unique R2 key (same pattern as profile picture)
        ext = os.path.splitext(file_name)[1] or '.bin'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = f"submissions/{student.id}/{assignment.id}/{timestamp}_{uuid.uuid4().hex}{ext}"

        try:
            upload_data = r2_storage.generate_upload_url(
                file_path=file_path,
                content_type=content_type,
                expires_in=900  # 15 minutes — same as profile picture
            )
        except Exception as e:
            return Response({"detail": f"Could not generate upload URL: {e}"}, status=502)

        return Response({
            "upload_url": upload_data['url'],
            "file_path": file_path,
            "expires_in": upload_data['expires_in'],
            "expires_at": upload_data['expires_at'],
            "assignment": {
                "id": str(assignment.id),
                "title": assignment.title,
                "subject": assignment.subject.name,
                "section": assignment.section.name,
                "due_date": assignment.due_date,
            }
        }, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # STEP 3 — student confirms upload, backend creates the submission
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='confirm')
    def confirm(self, request):
        """
        POST /api/v1/operations/submissions/confirm/
        Body: { "assignment_id": "uuid", "file_path": "submissions/..." }

        Backend verifies the file exists in R2, then upserts the submission
        and returns it with an embedded view_url — exactly like confirming
        a profile picture update.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student profile not found."}, status=404)

        assignment_id = request.data.get('assignment_id')
        file_path = request.data.get('file_path')

        if not assignment_id:
            raise ValidationError({"assignment_id": "Required."})
        if not file_path:
            raise ValidationError({"file_path": "Required."})

        try:
            assignment = Assignment.objects.get(id=assignment_id, school=request.user.school)
        except Assignment.DoesNotExist:
            return Response({"detail": "Assignment not found."}, status=404)

        # Verify the file actually landed in R2
        if not r2_storage.confirm_upload(file_path):
            return Response(
                {"detail": "File not found in storage. Please upload the file first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Upsert (re-submission replaces the previous file)
        existing = StudentSubmission.objects.filter(assignment=assignment, student=student).first()
        if existing:
            existing.file = file_path
            existing.status = 'Submitted'
            existing.save(update_fields=['file', 'status'])
            submission = existing
        else:
            submission = StudentSubmission.objects.create(
                school=request.user.school,
                assignment=assignment,
                student=student,
                file=file_path,
                status='Submitted',
            )

        view_url = _embed_view_url(file_path)

        return Response({
            "id": str(submission.id),
            "assignment_id": str(assignment.id),
            "assignment_title": assignment.title,
            "subject": assignment.subject.name,
            "section": assignment.section.name,
            "due_date": assignment.due_date,
            "submitted_at": submission.submitted_at,
            "file_path": file_path,
            "view_url": view_url,
            "view_url_expires_in": "7 days",
            "status": submission.status,
            "grade": float(submission.grade) if submission.grade is not None else None,
        }, status=status.HTTP_201_CREATED if not existing else status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # STUDENT: list own submissions
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='me')
    def my_submissions(self, request):
        """
        GET /api/v1/operations/submissions/me/
        Returns the student's submissions with embedded view URLs.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response({"detail": "Student profile not found."}, status=404)

        submissions = list(
            StudentSubmission.objects.filter(student=student, school=request.user.school)
            .select_related('assignment__subject', 'assignment__section', 'student__user')
            .order_by('-submitted_at')
        )
        _attach_view_urls(submissions)
        serializer = SubmissionWithViewUrlSerializer(submissions, many=True)
        return Response({"count": len(submissions), "results": serializer.data})

    # ------------------------------------------------------------------
    # TEACHER: all submissions for one assignment
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='assignment/(?P<assignment_id>[^/.]+)')
    def assignment_submissions(self, request, assignment_id):
        """
        GET /api/v1/operations/submissions/assignment/{assignment_id}/

        Returns every student's submission for this assignment.
        Each row includes an embedded view_url so the teacher can open
        the file directly — no extra API call needed.
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)

        try:
            assignment = Assignment.objects.get(
                id=assignment_id, teacher=teacher, school=request.user.school
            )
        except Assignment.DoesNotExist:
            return Response({"detail": "Assignment not found or no permission."}, status=403)

        submissions = list(
            StudentSubmission.objects.filter(assignment=assignment, school=request.user.school)
            .select_related('assignment__subject', 'assignment__section', 'student__user')
            .order_by('-submitted_at')
        )
        _attach_view_urls(submissions)
        serializer = SubmissionWithViewUrlSerializer(submissions, many=True)
        graded = sum(1 for s in submissions if s.grade is not None)
        return Response({
            "assignment": {
                "id": str(assignment.id),
                "title": assignment.title,
                "subject": assignment.subject.name,
                "section": assignment.section.name,
                "due_date": assignment.due_date,
            },
            "summary": {
                "total_submissions": len(submissions),
                "graded": graded,
                "pending": len(submissions) - graded,
            },
            "submissions": serializer.data,
        })

    # ------------------------------------------------------------------
    # TEACHER: grade a submission
    # ------------------------------------------------------------------

    @action(detail=True, methods=['patch'], url_path='grade')
    def grade_submission(self, request, pk=None):
        """
        PATCH /api/v1/operations/submissions/{id}/grade/
        Body: { "grade": 87.5, "remarks": "Good work" }

        Only the teacher who owns the assignment can grade it.
        Returns the updated submission row with a fresh view_url.
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)

        try:
            submission = StudentSubmission.objects.select_related(
                'assignment__subject', 'assignment__section', 'student__user'
            ).get(id=pk, school=request.user.school)
        except StudentSubmission.DoesNotExist:
            return Response({"detail": "Submission not found."}, status=404)

        if submission.assignment.teacher_id != teacher.id:
            return Response(
                {"detail": "You can only grade submissions for your own assignments."},
                status=status.HTTP_403_FORBIDDEN
            )

        grade = request.data.get('grade')
        remarks = request.data.get('remarks', '')

        if grade is None:
            raise ValidationError({"grade": "Required."})
        try:
            grade = float(grade)
        except (TypeError, ValueError):
            raise ValidationError({"grade": "Must be a number."})
        if grade < 0:
            raise ValidationError({"grade": "Cannot be negative."})

        submission.grade = grade
        submission.status = 'Graded'
        submission.save(update_fields=['grade', 'status'])

        view_url = _embed_view_url(submission.file)

        return Response({
            "id": str(submission.id),
            "student": {
                "id": str(submission.student.id),
                "name": f"{submission.student.user.first_name} {submission.student.user.last_name}",
                "enrollment_number": submission.student.enrollment_number,
            },
            "assignment": {
                "id": str(submission.assignment.id),
                "title": submission.assignment.title,
                "subject": submission.assignment.subject.name,
                "section": submission.assignment.section.name,
            },
            "file_path": _file_path_str(submission.file),
            "view_url": view_url,
            "view_url_expires_in": "7 days",
            "submitted_at": submission.submitted_at,
            "grade": float(submission.grade),
            "status": submission.status,
            "remarks": remarks,
        })

    # ------------------------------------------------------------------
    # TEACHER: all pending (ungraded) submissions
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='pending')
    def pending_submissions(self, request):
        """
        GET /api/v1/operations/submissions/pending/
        All ungraded submitted work across all the teacher's assignments.
        Optional ?assignment_id= to narrow down.
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response({"detail": "Teacher profile not found."}, status=404)

        teacher_assignments = Assignment.objects.filter(teacher=teacher, school=request.user.school)
        pending = StudentSubmission.objects.filter(
            school=request.user.school,
            assignment__in=teacher_assignments,
            grade__isnull=True,
            status='Submitted',
        ).select_related('assignment__subject', 'assignment__section', 'student__user').order_by('-submitted_at')

        if request.query_params.get('assignment_id'):
            pending = pending.filter(assignment_id=request.query_params['assignment_id'])

        pending = list(pending)
        _attach_view_urls(pending)
        serializer = SubmissionWithViewUrlSerializer(pending, many=True)
        return Response({"count": len(pending), "results": serializer.data})