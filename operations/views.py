from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema

from tenants.views import TenantAwareModelViewSet
from profiles.models import StudentProfile, ParentProfile, TeacherProfile
from academics.models import StudentEnrollment
from .models import Attendance, Exam, StudentGrade, Assignment, StudentSubmission
from .serializers import (
    AttendanceSerializer, BulkAttendanceSerializer,
    ExamSerializer, StudentGradeSerializer, BulkGradeSubmitSerializer,
    AssignmentSerializer, StudentSubmissionSerializer,
    StudentSubmissionCreateSerializer, AssignmentWithStatusSerializer,
)


# --- SHARED OWNERSHIP HELPERS ---
# Centralized here so every view that needs "is this caller allowed to see
# this student's data" uses the exact same logic, instead of each view
# re-implementing its own slightly different check.

def get_caller_student_id(user):
    """
    If the logged-in user IS a student themselves, return their own
    StudentProfile id. Otherwise return None.
    Queries the profile table directly rather than trusting a related_name
    attribute on `user`, since that attribute's existence has not been
    confirmed as correct in this codebase.
    """
    profile = StudentProfile.objects.filter(user=user).first()
    return profile.id if profile else None


def parent_can_access_student(user, student_id, require_academics=True):
    """
    True only if `user` has a ParentProfile that is mapped to `student_id`
    via ParentStudentMapping, and (if require_academics) that mapping has
    can_view_academics=True.
    """
    parent_profile = ParentProfile.objects.filter(user=user).first()
    if not parent_profile:
        return False

    from profiles.models import ParentStudentMapping
    qs = ParentStudentMapping.objects.filter(parent=parent_profile, student_id=student_id)
    if require_academics:
        qs = qs.filter(can_view_academics=True)
    return qs.exists()


def resolve_effective_student_id(request):
    """
    Figures out which student's data this request is allowed to see,
    given who is actually logged in.

    - If the caller IS a student: always return their own id, ignore any
      `student` query param they tried to pass (prevents a student from
      requesting someone else's id).
    - If the caller is a parent: require an explicit `student` query param,
      and verify the mapping exists before honoring it.
    - Otherwise (teacher/admin/staff): allow the `student` query param
      as-is, scoped only by the existing school-level isolation.

    Returns the student_id to use, or raises PermissionDenied/ValidationError.
    """
    user = request.user
    requested_student_id = request.query_params.get('student')

    own_student_id = get_caller_student_id(user)
    if own_student_id:
        return str(own_student_id)

    parent_profile = ParentProfile.objects.filter(user=user).first()
    if parent_profile:
        if not requested_student_id:
            raise ValidationError({"student": "This parameter is required for parent accounts."})
        if not parent_can_access_student(user, requested_student_id):
            raise PermissionDenied("You are not authorized to view this student's data.")
        return requested_student_id

    # Teacher / admin / staff — no per-student restriction beyond tenant scoping.
    return requested_student_id


class AttendanceViewSet(TenantAwareModelViewSet):
    queryset = Attendance.objects.select_related('student__user', 'academic_year', 'class_level', 'section').all()
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        date = self.request.query_params.get('date', None)
        student_id = self.request.query_params.get('student', None)
        section_id = self.request.query_params.get('section', None)
        if date: qs = qs.filter(date=date)
        if student_id: qs = qs.filter(student_id=student_id)
        if section_id: qs = qs.filter(section_id=section_id)
        return qs

    @extend_schema(request=BulkAttendanceSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-record')
    def bulk_record(self, request):
        serializer = BulkAttendanceSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school

        attendance_objects = [
            Attendance(
                school=school, academic_year_id=data['academic_year_id'],
                class_level_id=data['class_level_id'], section_id=data['section_id'],
                date=data['date'], student_id=r['student_id'],
                status=r['status'], remarks=r.get('remarks', '')
            ) for r in data['records']
        ]

        with transaction.atomic():
            Attendance.objects.bulk_create(
                attendance_objects, update_conflicts=True,
                unique_fields=['school', 'student', 'date'], update_fields=['status', 'remarks']
            )
        return Response({"detail": f"Processed attendance for {len(attendance_objects)} students."}, status=status.HTTP_200_OK)


class ExamViewSet(TenantAwareModelViewSet):
    queryset = Exam.objects.select_related('academic_year').all()
    serializer_class = ExamSerializer


class StudentGradeViewSet(TenantAwareModelViewSet):
    queryset = StudentGrade.objects.select_related('student__user', 'exam', 'subject').all()
    serializer_class = StudentGradeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        exam_id = self.request.query_params.get('exam', None)
        student_id = self.request.query_params.get('student', None)
        subject_id = self.request.query_params.get('subject', None)

        if exam_id: qs = qs.filter(exam_id=exam_id)
        if student_id: qs = qs.filter(student_id=student_id)
        if subject_id: qs = qs.filter(subject_id=subject_id)
        return qs

    @extend_schema(request=BulkGradeSubmitSerializer, responses={200: dict})
    @action(detail=False, methods=['post'], url_path='bulk-submit')
    def bulk_submit(self, request):
        serializer = BulkGradeSubmitSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        school = request.user.school

        grade_objects = []
        for record in data['records']:
            grade_objects.append(
                StudentGrade(
                    school=school,
                    exam_id=data['exam_id'],
                    subject_id=data['subject_id'],
                    student_id=record['student_id'],
                    marks_obtained=record['marks_obtained'],
                    max_marks=record.get('max_marks', 100.00),
                    remarks=record.get('remarks', '')
                )
            )

        with transaction.atomic():
            StudentGrade.objects.bulk_create(
                grade_objects,
                update_conflicts=True,
                unique_fields=['school', 'exam', 'student', 'subject'],
                update_fields=['marks_obtained', 'max_marks', 'remarks']
            )

        return Response(
            {"detail": f"Successfully processed grades for {len(grade_objects)} students."},
            status=status.HTTP_200_OK
        )


# --- ASSIGNMENTS ---

class AssignmentViewSet(TenantAwareModelViewSet):
    """
    Standard CRUD for assignments. Intended primary users: teachers/admins
    creating and managing assignments, filtered by section/subject/teacher.

    Students and parents wanting "my assignments + have I submitted them"
    should use GET /operations/assignments/for-student/ instead — this
    standard list endpoint does not attach submission status.
    """
    queryset = Assignment.objects.select_related('subject', 'section', 'teacher').all()
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        own_student_id = get_caller_student_id(self.request.user)
        if own_student_id:
            enrollment = StudentEnrollment.objects.filter(student_id=own_student_id).order_by(
                '-academic_year__start_date'
            ).first()
            if enrollment:
                return qs.filter(section_id=enrollment.section_id)
            return qs.none()

        section_id = self.request.query_params.get('section', None)
        subject_id = self.request.query_params.get('subject', None)
        teacher_id = self.request.query_params.get('teacher', None)

        if section_id:
            qs = qs.filter(section_id=section_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        return qs

    def perform_create(self, serializer):
        user = self.request.user
        teacher_profile = TeacherProfile.objects.filter(user=user).first()
        if not (user.is_superuser or user.is_staff or teacher_profile):
            raise PermissionDenied("Only teachers or staff can create assignments.")
        super().perform_create(serializer)

    @extend_schema(responses={200: AssignmentWithStatusSerializer(many=True)})
    @action(detail=False, methods=['get'], url_path='for-student')
    def for_student(self, request):
        """
        GET /api/v1/operations/assignments/for-student/?student=<id>

        Returns this student's section's assignments, each annotated with
        whether they've submitted it, the grade if graded, and the
        submission timestamp/file if present.

        - Student callers: `student` param is ignored; always resolves to
          their own id.
        - Parent callers: `student` param is required and verified against
          ParentStudentMapping (and can_view_academics) before any data
          is returned.
        - Teacher/admin/staff callers: `student` param used as given,
          scoped only by tenant isolation (same as other staff-facing views).
        """
        effective_student_id = resolve_effective_student_id(request)
        if not effective_student_id:
            raise ValidationError({"student": "This parameter is required."})

        enrollment = StudentEnrollment.objects.filter(student_id=effective_student_id).order_by(
            '-academic_year__start_date'
        ).first()
        if not enrollment:
            return Response({"count": 0, "results": []}, status=status.HTTP_200_OK)

        assignments = Assignment.objects.filter(
            school=request.user.school, section_id=enrollment.section_id
        ).select_related('subject', 'section', 'teacher').order_by('-due_date')

        serializer = AssignmentWithStatusSerializer(
            assignments, many=True, context={'student_id': effective_student_id}
        )
        return Response({"count": assignments.count(), "results": serializer.data}, status=status.HTTP_200_OK)


# --- SUBMISSIONS ---

class StudentSubmissionViewSet(TenantAwareModelViewSet):
    """
    Standard CRUD for submissions. Intended primary users: teachers/admins
    viewing/grading submissions across the school.

    Students wanting to submit their own work should use the `submit`
    action below rather than POSTing here directly, since this default
    create path does not restrict who the `student` field can be set to,
    nor does it prevent a submitter from also setting their own grade.
    """
    queryset = StudentSubmission.objects.select_related('assignment', 'student__user').all()
    serializer_class = StudentSubmissionSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        own_student_id = get_caller_student_id(self.request.user)
        if own_student_id:
            return qs.filter(student_id=own_student_id)

        student_id = self.request.query_params.get('student', None)
        assignment_id = self.request.query_params.get('assignment', None)

        parent_profile = ParentProfile.objects.filter(user=self.request.user).first()
        if parent_profile:
            if not student_id:
                return qs.none()
            if not parent_can_access_student(self.request.user, student_id):
                return qs.none()

        if student_id:
            qs = qs.filter(student_id=student_id)
        if assignment_id:
            qs = qs.filter(assignment_id=assignment_id)

        return qs

    @action(detail=False, methods=['post'], url_path='submit')
    def submit(self, request):
        """
        POST /api/v1/operations/submissions/submit/

        Student-only. Creates (or updates, if one already exists for this
        assignment) the caller's own submission. Cannot set grade/status —
        those are teacher-only, via the normal PATCH on this viewset's
        detail route, restricted separately below.
        """
        own_student_id = get_caller_student_id(request.user)
        if not own_student_id:
            raise PermissionDenied("Only students can submit assignments.")

        assignment_id = request.data.get('assignment')
        if not assignment_id:
            raise ValidationError({"assignment": "This field is required."})

        assignment = Assignment.objects.filter(id=assignment_id, school=request.user.school).first()
        if not assignment:
            raise ValidationError({"assignment": "Invalid assignment."})

        existing = StudentSubmission.objects.filter(
            assignment=assignment, student_id=own_student_id
        ).first()

        serializer = StudentSubmissionCreateSerializer(
            instance=existing, data=request.data, partial=bool(existing)
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            school=request.user.school,
            student_id=own_student_id,
            assignment=assignment,
            status='Submitted',
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED if not existing else status.HTTP_200_OK)

    def perform_update(self, serializer):
        """
        Restrict grade/status changes to teachers/staff. A student updating
        their own submission (e.g. re-uploading a file before the due date)
        should not be able to also set their own grade in the same call.
        """
        user = self.request.user
        is_teacher_or_staff = user.is_superuser or user.is_staff or TeacherProfile.objects.filter(user=user).exists()

        if not is_teacher_or_staff:
            for field in ('grade', 'status'):
                serializer.validated_data.pop(field, None)

        super().perform_update(serializer)