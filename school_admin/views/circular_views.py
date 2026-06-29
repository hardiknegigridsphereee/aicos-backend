# school_admin/views/circular_views.py

from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend

from school_admin.models import Circular
from school_admin.serializers.circular_serializers import CircularSerializer, CircularListSerializer

# Re-use the same permission class defined in school_admin_views.py
from school_admin.views.school_admin_views import IsSchoolAdminOrStaff


# ──────────────────────────────────────────────────────────────────────────────
# Helper: build the audience-filtered queryset for non-admin users
# ──────────────────────────────────────────────────────────────────────────────

def _recipient_queryset(user, school):
    """
    Return the published circulars that `user` is allowed to read.

    Audience rules
    ──────────────
    • teacher  → target_audience in ['all', 'teachers']
    • student  → target_audience in ['all', 'students']
    • parent   → target_audience in ['all', 'parents']

    Class-level targeting
    ─────────────────────
    If a circular has specific class levels attached, only users
    enrolled / assigned to those classes see it.
    Circulars with NO class levels set are school-wide.
    """
    from profiles.models import StudentProfile, TeacherProfile, ParentProfile
    from academics.models import StudentEnrollment, TeacherAssignment

    qs = Circular.objects.filter(school=school, is_published=True)

    is_teacher = TeacherProfile.objects.filter(user=user, school=school).exists()
    is_student = StudentProfile.objects.filter(user=user, school=school).exists()
    is_parent  = ParentProfile.objects.filter(user=user, school=school).exists()

    if is_teacher:
        audience_qs = qs.filter(target_audience__in=['all', 'teachers'])
        assigned_class_ids = TeacherAssignment.objects.filter(
            teacher__user=user, school=school
        ).values_list('class_level_id', flat=True).distinct()
        return (
            audience_qs.filter(target_class_levels__isnull=True)
            | audience_qs.filter(target_class_levels__in=assigned_class_ids)
        ).distinct()

    if is_student:
        audience_qs = qs.filter(target_audience__in=['all', 'students'])
        enrolled_class_ids = StudentEnrollment.objects.filter(
            student__user=user, school=school
        ).values_list('class_level_id', flat=True)
        return (
            audience_qs.filter(target_class_levels__isnull=True)
            | audience_qs.filter(target_class_levels__in=enrolled_class_ids)
        ).distinct()

    if is_parent:
        audience_qs = qs.filter(target_audience__in=['all', 'parents'])
        children_class_ids = StudentEnrollment.objects.filter(
            student__parent_mappings__parent__user=user, school=school
        ).values_list('class_level_id', flat=True).distinct()
        return (
            audience_qs.filter(target_class_levels__isnull=True)
            | audience_qs.filter(target_class_levels__in=children_class_ids)
        ).distinct()

    # Unknown role – return nothing
    return qs.none()


# ──────────────────────────────────────────────────────────────────────────────
# ViewSet
# ──────────────────────────────────────────────────────────────────────────────

class CircularViewSet(viewsets.ModelViewSet):
    """
    Circulars endpoint.

    POST / PUT / PATCH / DELETE  →  school admin / staff only  (IsSchoolAdminOrStaff)
    GET  (list / detail)         →  any authenticated user, filtered by their role
    """

    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['target_audience', 'is_published']
    search_fields    = ['title', 'content']
    ordering_fields  = ['created_at', 'title']
    ordering         = ['-created_at']

    # ------------------------------------------------------------------
    # Queryset – differs by role
    # ------------------------------------------------------------------

    def get_queryset(self):
        user   = self.request.user
        school = user.school

        # Admins see everything (published + unpublished)
        if user.is_superuser or user.is_staff or IsSchoolAdminOrStaff().has_permission(self.request, self):
            return (
                Circular.objects.filter(school=school)
                .select_related('created_by')
                .prefetch_related('target_class_levels')
            )

        # Everyone else gets the audience-filtered, published-only queryset
        return (
            _recipient_queryset(user, school)
            .select_related('created_by')
            .prefetch_related('target_class_levels')
        )

    # ------------------------------------------------------------------
    # Serializer – list uses lightweight version; others use full
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == 'list':
            return CircularListSerializer
        return CircularSerializer

    # ------------------------------------------------------------------
    # Permissions – write operations are admin-only; reads are open
    # ------------------------------------------------------------------

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'toggle_publish']:
            return [IsAuthenticated(), IsSchoolAdminOrStaff()]
        return [IsAuthenticated()]

    # ------------------------------------------------------------------
    # Create – inject school + created_by automatically
    # ------------------------------------------------------------------

    def perform_create(self, serializer):
        serializer.save(
            school=self.request.user.school,
            created_by=self.request.user,
        )

    # ------------------------------------------------------------------
    # Update – keep school consistent (prevent cross-tenant writes)
    # ------------------------------------------------------------------

    def perform_update(self, serializer):
        serializer.save(school=self.request.user.school)

    # ------------------------------------------------------------------
    # Extra action: toggle publish / unpublish without a full PUT body
    # ------------------------------------------------------------------

    @action(detail=True, methods=['patch'], url_path='toggle-publish')
    def toggle_publish(self, request, pk=None):
        """
        PATCH /api/v1/school-admin/circulars/{id}/toggle-publish/
        Flips is_published.  Admin / staff only (enforced by get_permissions).
        """
        circular = self.get_object()
        circular.is_published = not circular.is_published
        circular.save(update_fields=['is_published'])
        serializer = CircularSerializer(circular, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)
