from django.utils import timezone
from django.db import transaction, IntegrityError
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from profiles.models import TeacherProfile
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
    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

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
    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

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
    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'class_level__name']

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
    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'code']


# --- ENROLLMENT & ASSIGNMENT VIEWSETS ---

class StudentEnrollmentViewSet(TenantAwareModelViewSet):
    queryset = StudentEnrollment.objects.select_related(
        'student__user', 'academic_year', 'class_level', 'section'
    ).all()
    serializer_class = StudentEnrollmentSerializer

    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'student__user__first_name',
        'student__user__last_name',
        'class_level__name',
        'section__name'
    ]

    def get_queryset(self):
        qs = super().get_queryset()
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

class TeacherAssignmentViewSet(TenantAwareModelViewSet):
    queryset = TeacherAssignment.objects.select_related(
        'teacher__user', 'academic_year', 'class_level', 'section', 'subject'
    ).all()
    serializer_class = TeacherAssignmentSerializer

    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'teacher__user__first_name',
        'teacher__user__last_name',
        'subject__name',
        'class_level__name'
    ]

    def get_queryset(self):
        qs = super().get_queryset()
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
        """
        GET /api/v1/academics/teacher-assignments/my-students/?section=<id>

        Teacher-only. Returns the roster (StudentEnrollment rows) for a
        section, but ONLY if the logged-in teacher actually has a
        TeacherAssignment row for that section. If `section` is omitted,
        returns the roster for every section this teacher is assigned to.

        Staff/superusers may also call this; they bypass the assignment
        check entirely and can request any section in their school.
        """
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

        serializer = StudentEnrollmentSerializer(enrollments, many=True)
        return Response({"count": enrollments.count(), "results": serializer.data}, status=status.HTTP_200_OK)


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

    # --- ADDED FOR SEARCH ---
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'title',
        'content_type',
        'generated_content'  # Optional: Remove this if the content body is massive and slows down queries
    ]

    def get_queryset(self):
        qs = super().get_queryset()

        if hasattr(self.request.user, 'teacherprofile'):
            qs = qs.filter(teacher=self.request.user.teacherprofile)

        content_type = self.request.query_params.get('content_type', None)
        if content_type:
            qs = qs.filter(content_type__iexact=content_type)

        return qs

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'teacherprofile'):
            serializer.save(teacher=self.request.user.teacherprofile, school=self.request.user.school)
        else:
            from rest_framework import serializers
            raise serializers.ValidationError({"detail": "User is not a teacher."})