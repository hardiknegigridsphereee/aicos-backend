from django.utils import timezone
from django.db import transaction, IntegrityError
from rest_framework import viewsets, status, filters # FIXED: Added 'filters' import
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from .models import StudentEnrollment, TeacherAssignment, AcademicYear, ClassLevel, Section, Subject
from .serializers import (
    StudentEnrollmentSerializer, TeacherAssignmentSerializer, BulkPromotionSerializer,
    AcademicYearSerializer, ClassLevelSerializer, SectionSerializer, SubjectSerializer
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


# --- EXISTING ENROLLMENT & ASSIGNMENT VIEWSETS ---

class StudentEnrollmentViewSet(TenantAwareModelViewSet):
    queryset = StudentEnrollment.objects.select_related(
        'student__user', 'academic_year', 'class_level', 'section'
    ).all()
    serializer_class = StudentEnrollmentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status', None)
        student_id = self.request.query_params.get('student', None)

        if student_id:
            qs = qs.filter(student_id=student_id)

        # Add filtering by section_id
        section_id = self.request.query_params.get('section', None)
        if section_id:
            qs = qs.filter(section_id=section_id)
        
        # Add filtering by academic_year_id
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

    # --- ADDED FOR SEARCH FUNCTIONALITY ---
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