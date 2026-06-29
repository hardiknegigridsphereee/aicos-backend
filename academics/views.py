from django.utils import timezone
from django.db import transaction, IntegrityError
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import LimitOffsetPagination
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from profiles.models import StudentProfile, TeacherProfile
from accounts.permissions import IsStudent, IsTeacher, IsParent, IsTeacherOrStaff
from .models import StudentEnrollment, TeacherAssignment, AcademicYear, ClassLevel, Section, Subject, SavedAIContent
from .serializers import (
    StudentEnrollmentSerializer, TeacherAssignmentSerializer, BulkPromotionSerializer,
    AcademicYearSerializer, ClassLevelSerializer, SectionSerializer, SubjectSerializer,
    SavedAIContentSerializer
)

# --- NEW ACADEMIC BASE VIEWSETS ---

@extend_schema_view(
    list=extend_schema(summary="List all academic years"),
    create=extend_schema(summary="Create a new academic year"),
    retrieve=extend_schema(summary="Retrieve academic year details"),
    update=extend_schema(summary="Update an academic year"),
    partial_update=extend_schema(summary="Partially update an academic year"),
    destroy=extend_schema(summary="Delete an academic year"),
)
class AcademicYearViewSet(TenantAwareModelViewSet):
    queryset = AcademicYear.objects.all()
    serializer_class = AcademicYearSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]


@extend_schema_view(
    list=extend_schema(summary="List all class levels"),
    create=extend_schema(summary="Create a new class level"),
    retrieve=extend_schema(summary="Retrieve class level details"),
    update=extend_schema(summary="Update a class level"),
    partial_update=extend_schema(summary="Partially update a class level"),
    destroy=extend_schema(summary="Delete a class level"),
)
class ClassLevelViewSet(TenantAwareModelViewSet):
    queryset = ClassLevel.objects.all()
    serializer_class = ClassLevelSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]


@extend_schema_view(
    list=extend_schema(summary="List all sections"),
    create=extend_schema(summary="Create a new section"),
    retrieve=extend_schema(summary="Retrieve section details"),
    update=extend_schema(summary="Update a section"),
    partial_update=extend_schema(summary="Partially update a section"),
    destroy=extend_schema(summary="Delete a section"),
)
class SectionViewSet(TenantAwareModelViewSet):
    queryset = Section.objects.select_related('class_level').all()
    serializer_class = SectionSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'class_level__name']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]


@extend_schema_view(
    list=extend_schema(summary="List all subjects"),
    create=extend_schema(summary="Create a new subject"),
    retrieve=extend_schema(summary="Retrieve subject details"),
    update=extend_schema(summary="Update a subject"),
    partial_update=extend_schema(summary="Partially update a subject"),
    destroy=extend_schema(summary="Delete a subject"),
)
class SubjectViewSet(TenantAwareModelViewSet):
    queryset = Subject.objects.prefetch_related('class_levels').all()
    serializer_class = SubjectSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'code']
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]


# --- ENROLLMENT & ASSIGNMENT VIEWSETS ---

class StudentEnrollmentViewSet(TenantAwareModelViewSet):
    queryset = StudentEnrollment.objects.select_related(
        'student__user', 'academic_year', 'class_level', 'section'
    ).all()
    serializer_class = StudentEnrollmentSerializer

    filter_backends = [filters.SearchFilter]
    search_fields = [
        'student__user__first_name',
        'student__user__last_name',
        'class_level__name',
        'section__name'
    ]

    def get_permissions(self):
        if self.action in ['my_enrollment', 'my_enrollment_history']:
            return [IsAuthenticated(), IsStudent()]
        elif self.action in ['bulk_promote', 'create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacherOrStaff()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                student = StudentProfile.objects.get(user=user)
                return qs.filter(student=student)
            except StudentProfile.DoesNotExist:
                return qs.none()
        
        status_param = self.request.query_params.get('status', None)
        student_id = self.request.query_params.get('student', None)

        if student_id:
            qs = qs.filter(student_id=student_id)
        section_id = self.request.query_params.get('section', None)
        if section_id:
            qs = qs.filter(section_id=section_id)
        academic_year_id = self.request.query_params.get('academic_year', None)
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)

        today = timezone.now().date()
        if status_param == 'current':
            qs = qs.filter(
                academic_year__start_date__lte=today,
                academic_year__end_date__gte=today
            )
        elif status_param == 'historical':
            qs = qs.filter(academic_year__end_date__lt=today)

        return qs

    @extend_schema(request=BulkPromotionSerializer, responses={201: dict})
    @action(detail=False, methods=['post'], url_path='bulk-promote')
    def bulk_promote(self, request):
        serializer = BulkPromotionSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        school = request.user.school
        student_ids = data['student_ids']

        enrollments_to_create = []
        for student_id in student_ids:
            enrollments_to_create.append(
                StudentEnrollment(
                    school=school,
                    student_id=student_id,
                    academic_year_id=data['target_academic_year_id'],
                    class_level_id=data['target_class_level_id'],
                    section_id=data['target_section_id']
                )
            )

        try:
            with transaction.atomic():
                StudentEnrollment.objects.bulk_create(enrollments_to_create)
            return Response(
                {"detail": f"Successfully promoted {len(student_ids)} students."},
                status=status.HTTP_201_CREATED
            )
        except IntegrityError:
            return Response(
                {"detail": "Promotion failed. One or more students are already enrolled in the target academic year."},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], url_path='me')
    def my_enrollment(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()

        if not enrollment:
            return Response(
                {"detail": "No enrollment found."},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = self.get_serializer(enrollment)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='me/history')
    def my_enrollment_history(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        enrollments = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date')

        serializer = self.get_serializer(enrollments, many=True)
        return Response({
            "count": enrollments.count(),
            "results": serializer.data
        })


class TeacherAssignmentViewSet(TenantAwareModelViewSet):
    queryset = TeacherAssignment.objects.select_related(
        'teacher__user', 'academic_year', 'class_level', 'section', 'subject'
    ).all()
    serializer_class = TeacherAssignmentSerializer

    filter_backends = [filters.SearchFilter]
    search_fields = [
        'teacher__user__first_name',
        'teacher__user__last_name',
        'subject__name',
        'class_level__name'
    ]

    def get_permissions(self):
        if self.action == 'my_students':
            return [IsAuthenticated(), IsTeacher()]
        elif self.action == 'my_assignments':
            return [IsAuthenticated(), IsTeacher()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsTeacherOrStaff()]
        else:
            return [IsAuthenticated(), IsTeacherOrStaff()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not (user.is_superuser or user.is_staff):
            try:
                teacher = TeacherProfile.objects.get(user=user)
                return qs.filter(teacher=teacher)
            except TeacherProfile.DoesNotExist:
                return qs.none()
        
        status_param = self.request.query_params.get('status', None)
        teacher_id = self.request.query_params.get('teacher', None)

        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)

        today = timezone.now().date()
        if status_param == 'current':
            qs = qs.filter(
                academic_year__start_date__lte=today,
                academic_year__end_date__gte=today
            )
        elif status_param == 'historical':
            qs = qs.filter(academic_year__end_date__lt=today)

        return qs

    @extend_schema(
        summary="List students in a section I'm assigned to teach",
        responses={200: StudentEnrollmentSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='my-students')
    def my_students(self, request):
        user = request.user
        school = user.school

        is_staff_or_super = user.is_superuser or user.is_staff
        teacher_profile = TeacherProfile.objects.filter(user=user).first()

        if not is_staff_or_super and not teacher_profile:
            raise PermissionDenied("Only teachers or staff can view a class roster.")

        requested_section_id = request.query_params.get('section')

        if is_staff_or_super:
            allowed_section_ids = [requested_section_id] if requested_section_id else None
        else:
            assigned_section_ids = list(
                TeacherAssignment.objects.filter(
                    school=school, teacher=teacher_profile
                ).values_list('section_id', flat=True).distinct()
            )

            if requested_section_id:
                if str(requested_section_id) not in [str(s) for s in assigned_section_ids]:
                    raise PermissionDenied("You are not assigned to teach this section.")
                allowed_section_ids = [requested_section_id]
            else:
                allowed_section_ids = assigned_section_ids

        enrollments = StudentEnrollment.objects.filter(school=school).select_related(
            'student__user', 'academic_year', 'class_level', 'section'
        )

        if allowed_section_ids is not None:
            enrollments = enrollments.filter(section_id__in=allowed_section_ids)

        academic_year_id = request.query_params.get('academic_year')
        if academic_year_id:
            enrollments = enrollments.filter(academic_year_id=academic_year_id)

        serializer = StudentEnrollmentSerializer(enrollments, many=True)
        return Response({"count": enrollments.count(), "results": serializer.data}, status=status.HTTP_200_OK)

    # ✅ NEW: My Teaching Assignments
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


# --- SAVED AI CONTENT VIEWSET ---

@extend_schema_view(
    list=extend_schema(summary="List saved AI content"),
    create=extend_schema(summary="Save new AI content"),
    retrieve=extend_schema(summary="Retrieve saved AI content details"),
    update=extend_schema(summary="Update saved AI content"),
    partial_update=extend_schema(summary="Partially update saved AI content"),
    destroy=extend_schema(summary="Delete saved AI content"),
)
class SavedAIContentViewSet(TenantAwareModelViewSet):
    queryset = SavedAIContent.objects.all()
    serializer_class = SavedAIContentSerializer
    pagination_class = LimitOffsetPagination

    filter_backends = [filters.SearchFilter]
    search_fields = [
        'title',
        'content_type',
        'generated_content'
    ]
    
    permission_classes = [IsAuthenticated, IsTeacher]

    def get_queryset(self):
        qs = super().get_queryset()

        teacher_profile = TeacherProfile.objects.filter(user=self.request.user).first()
        if teacher_profile:
            qs = qs.filter(teacher=teacher_profile)
        else:
            qs = qs.none()

        content_type = self.request.query_params.get('content_type', None)
        if content_type:
            qs = qs.filter(content_type__iexact=content_type)

        return qs

    def perform_create(self, serializer):
        teacher_profile = TeacherProfile.objects.filter(user=self.request.user).first()
        if teacher_profile:
            serializer.save(teacher=teacher_profile, school=self.request.user.school)
        else:
            from rest_framework import serializers
            raise serializers.ValidationError({"detail": "User is not a teacher."})