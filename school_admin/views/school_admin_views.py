from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import filters
from rest_framework.pagination import PageNumberPagination

from django.db.models import Count, Prefetch

from profiles.models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from academics.models import StudentEnrollment, TeacherAssignment
from school_admin.serializers.school_admin_serializers import (
    SchoolAdminStudentListSerializer,
    SchoolAdminTeacherListSerializer,
    SchoolAdminTeacherAssignmentSerializer,
    SchoolAdminParentStudentMappingSerializer,
    SchoolAdminParentListSerializer,
)


# ---------------------------------------------------------------------------
# Permission
# ---------------------------------------------------------------------------

class IsSchoolAdminOrStaff(IsAuthenticated):
    """
    Blocks students and parents. Allows superusers, Django staff, and
    any other authenticated school user (e.g. teachers acting as admins).
    Tighten the last condition to a Role check if you need stricter control.
    """
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        if user.is_superuser or user.is_staff:
            return True
        from profiles.models import StudentProfile, ParentProfile
        if StudentProfile.objects.filter(user=user).exists():
            return False
        if ParentProfile.objects.filter(user=user).exists():
            return False
        return bool(user.school)


# ---------------------------------------------------------------------------
# Shared pagination
# ---------------------------------------------------------------------------

class BatchPagination(PageNumberPagination):
    """
    Default 50 records per page, consumer can override via ?page_size=
    up to a max of 200.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200
    page_query_param = 'page'


# ---------------------------------------------------------------------------
# 1. All Students (batched)
# ---------------------------------------------------------------------------

class SchoolAdminStudentListView(ListAPIView):
    """
    GET /api/v1/school-admin/students/

    Query params:
      ?page=1
      ?page_size=50        (max 200)
      ?search=<term>       name / email / enrollment number
      ?is_archived=true/false
      ?class_level=<uuid>
      ?section=<uuid>
      ?academic_year=<uuid>
    """
    serializer_class = SchoolAdminStudentListSerializer
    permission_classes = [IsSchoolAdminOrStaff]
    pagination_class = BatchPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__email',
        'enrollment_number',
        'phone_number',
    ]

    def get_queryset(self):
        school = self.request.user.school
        qs = StudentProfile.objects.filter(school=school).select_related('user')

        is_archived = self.request.query_params.get('is_archived')
        if is_archived is not None:
            qs = qs.filter(is_archived=is_archived.lower() == 'true')

        class_level_id = self.request.query_params.get('class_level')
        section_id = self.request.query_params.get('section')
        academic_year_id = self.request.query_params.get('academic_year')

        if any([class_level_id, section_id, academic_year_id]):
            enrollment_qs = StudentEnrollment.objects.filter(school=school)
            if class_level_id:
                enrollment_qs = enrollment_qs.filter(class_level_id=class_level_id)
            if section_id:
                enrollment_qs = enrollment_qs.filter(section_id=section_id)
            if academic_year_id:
                enrollment_qs = enrollment_qs.filter(academic_year_id=academic_year_id)
            student_ids = enrollment_qs.values_list('student_id', flat=True)
            qs = qs.filter(id__in=student_ids)

        return qs.order_by('user__last_name', 'user__first_name')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        students = page if page is not None else queryset

        # Bulk-fetch enrollments to avoid N+1
        student_ids = [s.id for s in students]
        school = request.user.school
        enrollments = (
            StudentEnrollment.objects
            .filter(student_id__in=student_ids, school=school)
            .select_related('class_level', 'section', 'academic_year')
            .order_by('student_id', '-academic_year__start_date')
        )
        enrollment_map = {}
        for e in enrollments:
            if e.student_id not in enrollment_map:
                enrollment_map[e.student_id] = e

        for student in students:
            student._current_enrollment = enrollment_map.get(student.id)

        serializer = self.get_serializer(students, many=True)
        return self.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# 2. All Teachers (batched)
# ---------------------------------------------------------------------------

class SchoolAdminTeacherListView(ListAPIView):
    """
    GET /api/v1/school-admin/teachers/

    Query params:
      ?page=1
      ?page_size=50
      ?search=<term>       name / email / employee_id
      ?is_active=true/false
    """
    serializer_class = SchoolAdminTeacherListSerializer
    permission_classes = [IsSchoolAdminOrStaff]
    pagination_class = BatchPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__email',
        'employee_id',
        'qualification',
    ]

    def get_queryset(self):
        school = self.request.user.school
        qs = (
            TeacherProfile.objects
            .filter(school=school)
            .select_related('user')
            .annotate(assignment_count=Count('assignments'))
            .order_by('user__last_name', 'user__first_name')
        )

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(user__is_active=is_active.lower() == 'true')

        return qs


# ---------------------------------------------------------------------------
# 3. Teacher Assignment Matrix
# ---------------------------------------------------------------------------

class SchoolAdminTeacherAssignmentListView(ListAPIView):
    """
    GET /api/v1/school-admin/teacher-assignments/

    Query params:
      ?page=1
      ?page_size=50
      ?search=<term>
      ?teacher=<uuid>
      ?class_level=<uuid>
      ?section=<uuid>
      ?subject=<uuid>
      ?academic_year=<uuid>
      ?is_class_teacher=true/false
    """
    serializer_class = SchoolAdminTeacherAssignmentSerializer
    permission_classes = [IsSchoolAdminOrStaff]
    pagination_class = BatchPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'teacher__user__first_name',
        'teacher__user__last_name',
        'teacher__user__email',
        'teacher__employee_id',
        'subject__name',
        'class_level__name',
        'section__name',
        'academic_year__name',
    ]

    def get_queryset(self):
        school = self.request.user.school
        qs = (
            TeacherAssignment.objects
            .filter(school=school)
            .select_related(
                'teacher__user',
                'class_level',
                'section',
                'subject',
                'academic_year',
            )
        )

        teacher_id = self.request.query_params.get('teacher')
        class_level_id = self.request.query_params.get('class_level')
        section_id = self.request.query_params.get('section')
        subject_id = self.request.query_params.get('subject')
        academic_year_id = self.request.query_params.get('academic_year')
        is_class_teacher = self.request.query_params.get('is_class_teacher')

        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        if class_level_id:
            qs = qs.filter(class_level_id=class_level_id)
        if section_id:
            qs = qs.filter(section_id=section_id)
        if subject_id:
            qs = qs.filter(subject_id=subject_id)
        if academic_year_id:
            qs = qs.filter(academic_year_id=academic_year_id)
        if is_class_teacher is not None:
            qs = qs.filter(is_class_teacher=is_class_teacher.lower() == 'true')

        return qs.order_by(
            'academic_year__start_date',
            'class_level__numeric_order',
            'section__name',
            'subject__name',
        )


# ---------------------------------------------------------------------------
# 4. Parent-Student Mappings (read-only)
# ---------------------------------------------------------------------------

class SchoolAdminParentStudentMappingListView(ListAPIView):
    """
    GET /api/v1/school-admin/parent-student-mappings/

    Query params:
      ?page=1
      ?page_size=50
      ?search=<term>
      ?student=<uuid>
      ?parent=<uuid>
      ?relationship=Mother
      ?is_primary_contact=true/false
    """
    serializer_class = SchoolAdminParentStudentMappingSerializer
    permission_classes = [IsSchoolAdminOrStaff]
    pagination_class = BatchPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'parent__user__first_name',
        'parent__user__last_name',
        'parent__user__email',
        'student__user__first_name',
        'student__user__last_name',
        'student__user__email',
        'student__enrollment_number',
        'relationship',
    ]

    def get_queryset(self):
        school = self.request.user.school
        qs = (
            ParentStudentMapping.objects
            .filter(school=school)
            .select_related('parent__user', 'student__user')
        )

        student_id = self.request.query_params.get('student')
        parent_id = self.request.query_params.get('parent')
        relationship = self.request.query_params.get('relationship')
        is_primary = self.request.query_params.get('is_primary_contact')

        if student_id:
            qs = qs.filter(student_id=student_id)
        if parent_id:
            qs = qs.filter(parent_id=parent_id)
        if relationship:
            qs = qs.filter(relationship__iexact=relationship)
        if is_primary is not None:
            qs = qs.filter(is_primary_contact=is_primary.lower() == 'true')

        return qs.order_by(
            'student__user__last_name',
            'student__user__first_name',
            'relationship',
        )


# ---------------------------------------------------------------------------
# 5. All Parents (batched)
# ---------------------------------------------------------------------------

class SchoolAdminParentListView(ListAPIView):
    """
    GET /api/v1/school-admin/parents/

    Returns all parents for the school with their full details and a
    summary of each linked child. Children are fetched in one bulk query
    per page to avoid N+1.

    Query params:
      ?page=1
      ?page_size=50        (max 200)
      ?search=<term>       name / email / phone
      ?is_active=true/false
      ?has_children=true/false   filter parents who have/don't have mapped children
      ?relationship=Mother       filter by relationship type across mappings
    """
    serializer_class = SchoolAdminParentListSerializer
    permission_classes = [IsSchoolAdminOrStaff]
    pagination_class = BatchPagination
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__email',
        'phone_number',
        'occupation',
        'emergency_contact_number',
    ]

    def get_queryset(self):
        school = self.request.user.school
        qs = (
            ParentProfile.objects
            .filter(school=school)
            .select_related('user')
            .order_by('user__last_name', 'user__first_name')
        )

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            qs = qs.filter(user__is_active=is_active.lower() == 'true')

        has_children = self.request.query_params.get('has_children')
        if has_children is not None:
            if has_children.lower() == 'true':
                qs = qs.filter(student_mappings__isnull=False).distinct()
            else:
                qs = qs.filter(student_mappings__isnull=True)

        relationship = self.request.query_params.get('relationship')
        if relationship:
            qs = qs.filter(
                student_mappings__relationship__iexact=relationship
            ).distinct()

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        parents = page if page is not None else queryset

        # Bulk-fetch all mappings + student info for this page in one query
        parent_ids = [p.id for p in parents]
        mappings = (
            ParentStudentMapping.objects
            .filter(parent_id__in=parent_ids, school=request.user.school)
            .select_related('student__user')
            .order_by('student__user__last_name', 'student__user__first_name')
        )

        # Group mappings by parent id
        mapping_map: dict = {}
        for m in mappings:
            mapping_map.setdefault(m.parent_id, []).append(m)

        # Attach to parent objects so serializer reads without extra queries
        for parent in parents:
            parent._children_mappings = mapping_map.get(parent.id, [])

        serializer = self.get_serializer(parents, many=True)
        return self.get_paginated_response(serializer.data)