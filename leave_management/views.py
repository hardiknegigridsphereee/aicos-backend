from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from profiles.models import StudentProfile, TeacherProfile
from tenants.views import TenantAwareModelViewSet

from .models import LeaveRequest
from .permissions import IsStudentOrTeacher, is_school_admin
from .utils import get_homeroom_student_ids, is_section_teacher_of_student
from .serializers import (
    LeaveRequestCreateSerializer,
    LeaveRequestSerializer,
    LeaveReviewSerializer,
)


class LeaveRequestViewSet(TenantAwareModelViewSet):
    """
    Single endpoint family covering both leave workflows:

      Students  -> POST /leave-requests/                (apply)
                -> GET  /leave-requests/me/              (own history)
      Teachers  -> POST /leave-requests/                 (apply for own leave)
                -> GET  /leave-requests/me/              (own history)
                -> GET  /leave-requests/pending-review/  (their homeroom students' leaves to action)
                -> POST /leave-requests/{id}/approve/    (only if they're that student's section/class teacher)
                -> POST /leave-requests/{id}/reject/
      School Admin -> GET  /leave-requests/pending-review/  (teacher leaves to action)
                   -> POST /leave-requests/{id}/approve/    (action a teacher's leave)
                   -> POST /leave-requests/{id}/reject/
      Any applicant -> POST /leave-requests/{id}/cancel/  (withdraw own pending request)
    """

    queryset = LeaveRequest.objects.select_related(
        'student__user', 'teacher__user', 'reviewed_by'
    ).all()
    serializer_class = LeaveRequestSerializer

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------
    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsStudentOrTeacher()]
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated()]  # fine-grained check happens in the action
        if self.action == 'pending_review':
            return [IsAuthenticated()]
        if self.action == 'cancel':
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'create':
            return LeaveRequestCreateSerializer
        return LeaveRequestSerializer

    # ------------------------------------------------------------------
    # Queryset scoping
    # ------------------------------------------------------------------
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user

        if user.is_superuser or user.is_staff:
            pass  # full visibility within their school (already scoped by tenant filter)
        else:
            student_profile = StudentProfile.objects.filter(user=user).first()
            teacher_profile = TeacherProfile.objects.filter(user=user).first()

            if student_profile and not teacher_profile:
                # Students can only ever see their own requests.
                qs = qs.filter(student=student_profile)
            elif teacher_profile:
                # Teachers can see their own leave requests AND student
                # leave requests for sections where they're the
                # class/section teacher.
                homeroom_ids = get_homeroom_student_ids(user)
                qs = qs.filter(
                    models_q_teacher_or_homeroom_student(teacher_profile, homeroom_ids)
                )
            else:
                # School-admin style account (no student/teacher profile).
                qs = qs.filter(applicant_role=LeaveRequest.ApplicantRole.TEACHER)

        for param, field in [
            ('status', 'status'),
            ('applicant_role', 'applicant_role'),
            ('leave_type', 'leave_type'),
        ]:
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})

        return qs

    # ------------------------------------------------------------------
    # Create: figure out who is applying and stamp student/teacher/school
    # ------------------------------------------------------------------
    def perform_create(self, serializer):
        user = self.request.user
        if not user.school:
            raise PermissionDenied("You must be assigned to a school to apply for leave.")

        student_profile = StudentProfile.objects.filter(user=user, school=user.school).first()
        teacher_profile = TeacherProfile.objects.filter(user=user, school=user.school).first()

        if student_profile:
            serializer.save(
                school=user.school,
                applicant_role=LeaveRequest.ApplicantRole.STUDENT,
                student=student_profile,
                teacher=None,
            )
        elif teacher_profile:
            serializer.save(
                school=user.school,
                applicant_role=LeaveRequest.ApplicantRole.TEACHER,
                teacher=teacher_profile,
                student=None,
            )
        else:
            raise PermissionDenied("Only students or teachers can apply for leave.")

    # ------------------------------------------------------------------
    # GET /leave-requests/me/
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='me')
    def my_requests(self, request):
        user = request.user
        student_profile = StudentProfile.objects.filter(user=user, school=user.school).first()
        teacher_profile = TeacherProfile.objects.filter(user=user, school=user.school).first()

        if student_profile:
            qs = LeaveRequest.objects.filter(student=student_profile)
        elif teacher_profile:
            qs = LeaveRequest.objects.filter(teacher=teacher_profile)
        else:
            return Response({"detail": "No leave history for this account type."}, status=status.HTTP_400_BAD_REQUEST)

        status_param = request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        serializer = LeaveRequestSerializer(qs.order_by('-applied_at'), many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # GET /leave-requests/pending-review/
    # ------------------------------------------------------------------
    @action(detail=False, methods=['get'], url_path='pending-review')
    def pending_review(self, request):
        user = request.user

        if user.is_superuser or user.is_staff or is_school_admin(user):
            qs = LeaveRequest.objects.filter(
                school=user.school,
                applicant_role=LeaveRequest.ApplicantRole.TEACHER,
                status=LeaveRequest.StatusChoices.PENDING,
            )
        elif TeacherProfile.objects.filter(user=user, school=user.school).exists():
            homeroom_ids = get_homeroom_student_ids(user)
            qs = LeaveRequest.objects.filter(
                school=user.school,
                applicant_role=LeaveRequest.ApplicantRole.STUDENT,
                status=LeaveRequest.StatusChoices.PENDING,
                student_id__in=homeroom_ids,
            )
        else:
            raise PermissionDenied("You do not review leave requests.")

        serializer = LeaveRequestSerializer(qs.order_by('-applied_at'), many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # POST /leave-requests/{id}/approve/   and   /reject/
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        return self._review(request, pk, LeaveRequest.StatusChoices.APPROVED)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        return self._review(request, pk, LeaveRequest.StatusChoices.REJECTED)

    def _review(self, request, pk, new_status):
        leave = self.get_object()
        user = request.user

        if leave.status != LeaveRequest.StatusChoices.PENDING:
            raise ValidationError(f"This request has already been {leave.status.lower()}.")

        if leave.applicant_role == LeaveRequest.ApplicantRole.STUDENT:
            if not (
                user.is_superuser
                or user.is_staff
                or is_section_teacher_of_student(user, leave.student)
            ):
                raise PermissionDenied(
                    "Only this student's section/class teacher (or a school admin) can review this leave request."
                )
        else:  # TEACHER applicant
            if not (user.is_superuser or user.is_staff or is_school_admin(user)):
                raise PermissionDenied("Only a school admin can review a teacher's leave request.")

        serializer = LeaveReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        leave.status = new_status
        leave.reviewed_by = user
        leave.reviewed_at = timezone.now()
        leave.review_remarks = serializer.validated_data.get('remarks', '')
        leave.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_remarks'])

        return Response(LeaveRequestSerializer(leave).data)

    # ------------------------------------------------------------------
    # POST /leave-requests/{id}/cancel/
    # ------------------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        leave = self.get_object()
        user = request.user

        is_owner = (
            (leave.student_id and StudentProfile.objects.filter(id=leave.student_id, user=user).exists())
            or (leave.teacher_id and TeacherProfile.objects.filter(id=leave.teacher_id, user=user).exists())
        )
        if not is_owner and not user.is_superuser:
            raise PermissionDenied("You can only cancel your own leave request.")

        if leave.status != LeaveRequest.StatusChoices.PENDING:
            raise ValidationError("Only pending requests can be cancelled.")

        leave.status = LeaveRequest.StatusChoices.CANCELLED
        leave.save(update_fields=['status'])
        return Response(LeaveRequestSerializer(leave).data)


def models_q_teacher_or_homeroom_student(teacher_profile, homeroom_student_ids):
    from django.db.models import Q
    return Q(teacher=teacher_profile) | Q(
        applicant_role=LeaveRequest.ApplicantRole.STUDENT,
        student_id__in=homeroom_student_ids,
    )
