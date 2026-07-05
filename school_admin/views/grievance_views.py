from django.utils import timezone
from django.db.models import Q

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from tenants.models import User

from school_admin.models import Grievance
from school_admin.serializers.grievance_serializers import (
    GrievanceSerializer,
    GrievanceCreateSerializer,
    GrievanceUpdateSerializer,
    GrievanceAdminListSerializer,
    GrievanceStatsSerializer,
)
from accounts.permissions import IsTeacherOrStaff
from profiles.models import ParentStudentMapping

from notifications.models import Notification
from school_admin.notification_utils import (
    build_grievance_payload,
    get_grievance_admins,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_school_admin(user) -> bool:
    """
    Returns True for Django superusers, Django staff, AND any school user
    who is NOT a student or parent (i.e. teachers / admin staff registered
    in the tenant without a student/parent profile).

    NOTE: this stays broad on purpose -- it backs `IsTeacherOrStaff`-style
    permission checks (who is *allowed* to manage a grievance). It is
    intentionally NOT used to decide who gets *notified* about grievances;
    see `get_grievance_admins()` in notification_utils.py for that
    narrower, admin-only rule.
    """
    if user.is_superuser or user.is_staff:
        return True
    return (
        bool(user.school)
        and not hasattr(user, 'studentprofile')
        and not hasattr(user, 'parentprofile')
    )


def _get_parent_student_ids(user):
    """Return a flat list of StudentProfile PKs linked to this parent."""
    return list(
        ParentStudentMapping.objects
        .filter(parent=user.parentprofile, school=user.school)
        .values_list('student_id', flat=True)
    )


# ---------------------------------------------------------------------------
# ViewSet
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="List grievances (admin: all, student/parent: own)"),
    create=extend_schema(summary="Submit a new grievance"),
    retrieve=extend_schema(summary="Get grievance details"),
    update=extend_schema(summary="Update grievance (admin only)"),
    partial_update=extend_schema(summary="Partially update grievance (admin only)"),
    destroy=extend_schema(summary="Delete grievance (admin only)"),
)
class GrievanceViewSet(TenantAwareModelViewSet):
    """
    Grievance management endpoint.

    Role behaviour
    ──────────────
    • Students   → create + view their own grievances.
    • Parents    → create + view their own grievances + their children's grievances.
    • School admins / staff → full CRUD + status management actions.
    """

    queryset = Grievance.objects.select_related(
        'submitted_by', 'student__user', 'assigned_to'
    ).all()

    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'status':      ['exact'],
        'priority':    ['exact'],
        'category':    ['exact'],
        'source_type': ['exact'],
        'created_at':  ['gte', 'lte'],
    }
    search_fields = [
        'title',
        'description',
        'submitted_by__email',
        'submitted_by__first_name',
        'submitted_by__last_name',
        'student__user__first_name',
        'student__user__last_name',
        'student__enrollment_number',
    ]
    ordering_fields = ['created_at', 'updated_at', 'priority', 'status']
    ordering        = ['-created_at']

    # ------------------------------------------------------------------
    # Serializer selection
    # ------------------------------------------------------------------

    def get_serializer_class(self):
        if self.action == 'create':
            return GrievanceCreateSerializer
        if self.action in ('update', 'partial_update'):
            return GrievanceUpdateSerializer
        if self.action == 'list' and _is_school_admin(self.request.user):
            return GrievanceAdminListSerializer
        return GrievanceSerializer

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def get_permissions(self):
        # Admin-only mutation actions
        if self.action in ('update', 'partial_update', 'destroy',
                           'resolve_grievance', 'reject_grievance', 'assign_grievance'):
            return [IsAuthenticated(), IsTeacherOrStaff()]

        # All authenticated users can do everything else
        return [IsAuthenticated()]

    # ------------------------------------------------------------------
    # Queryset scoping (tenant filter applied by TenantAwareModelViewSet)
    # ------------------------------------------------------------------

    def get_queryset(self):
        qs   = super().get_queryset()          # already scoped to school via TenantAwareModelViewSet
        user = self.request.user

        # Admins / staff → full school visibility; DjangoFilterBackend handles filters
        if _is_school_admin(user):
            return qs

        # Students → only their own submissions
        if hasattr(user, 'studentprofile'):
            return qs.filter(submitted_by=user)

        # Parents → own submissions + grievances filed for their children
        if hasattr(user, 'parentprofile'):
            student_ids = _get_parent_student_ids(user)
            return qs.filter(
                Q(submitted_by=user) | Q(student_id__in=student_ids)
            ).distinct()

        # Fallback: no access
        return qs.none()

    # ------------------------------------------------------------------
    # Create  (students & parents only)
    # ------------------------------------------------------------------

    def create(self, request, *args, **kwargs):
        if _is_school_admin(request.user):
            return Response(
                {'detail': 'Administrators cannot submit grievances.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Inject school and submitted_by.  The serializer's create() method
        receives these as part of validated_data (DRF merges save() kwargs
        into validated_data before calling create()).
        """
        serializer.save(
            school       = self.request.user.school,
            submitted_by = self.request.user,
        )
        self._notify_admins(serializer.instance)

    def _notify_admins(self, grievance):
        """
        One Notification row per grievance-admin, fired on submission.

        `get_grievance_admins()` now excludes teachers (see
        notification_utils.py) -- grievances are a school-admin-only inbox,
        so teachers must not get a bell notification for one just because
        they happen to have permission to manage grievances.
        """
        payload = build_grievance_payload(grievance)
        admins = get_grievance_admins(grievance.school)

        Notification.objects.bulk_create([
            Notification(
                school=grievance.school,
                notification_type=Notification.NotificationType.GRIEVANCE,
                sender=grievance.submitted_by,
                receiver=admin,
                payload=payload,
                is_read=False,
            )
            for admin in admins
        ])

    def _notify_submitter(self, grievance):
        """
        Single Notification back to whoever submitted the grievance, fired
        on resolve/reject/close so they're not left wondering what
        happened to it.
        """
        Notification.objects.create(
            school=grievance.school,
            notification_type=Notification.NotificationType.GRIEVANCE,
            sender=self.request.user,
            receiver=grievance.submitted_by,
            payload=build_grievance_payload(grievance),
            is_read=False,
        )

    def _clear_grievance_notifications(self, grievance, exclude_receiver=None):
        """
        Delete every outstanding Notification tied to this grievance.

        Notification.payload only stores grievance_id as a plain JSON
        string (no FK to Grievance), so nothing cascades automatically --
        without this, a resolved/rejected/withdrawn/deleted grievance keeps
        showing its stale "new grievance" / "update" entries in every
        recipient's bell forever.

        `exclude_receiver`, if given, leaves that user's existing
        notifications alone (used when we're about to send them a fresh,
        more relevant one instead of just wiping the slate).
        """
        qs = Notification.objects.filter(
            notification_type=Notification.NotificationType.GRIEVANCE,
            payload__grievance_id=str(grievance.id),
        )
        if exclude_receiver is not None:
            qs = qs.exclude(receiver=exclude_receiver)
        qs.delete()

    # ------------------------------------------------------------------
    # Update  (admins only – enforced by get_permissions)
    # ------------------------------------------------------------------

    def perform_update(self, serializer):
        serializer.save()

    # ------------------------------------------------------------------
    # Destroy – same "stale notification" problem as circulars: wipe any
    # Notification rows pointing at this grievance before it's gone.
    # ------------------------------------------------------------------

    def perform_destroy(self, instance):
        self._clear_grievance_notifications(instance)
        instance.delete()

    # ------------------------------------------------------------------
    # Custom actions – student / parent facing
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='me')
    def my_grievances(self, request):
        """
        GET /api/v1/school-admin/grievances/me/
        Returns grievances relevant to the requesting user.
        Supports ?status= filter.
        """
        user = request.user

        if hasattr(user, 'parentprofile'):
            student_ids = _get_parent_student_ids(user)
            qs = Grievance.objects.filter(
                Q(submitted_by=user) | Q(student_id__in=student_ids),
                school=user.school,
            ).distinct()
        else:
            qs = Grievance.objects.filter(submitted_by=user, school=user.school)

        qs = qs.select_related('submitted_by', 'student__user', 'assigned_to')

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        qs = qs.order_by('-created_at')

        serializer = GrievanceSerializer(qs, many=True)
        return Response({'count': qs.count(), 'results': serializer.data})

    @action(detail=False, methods=['get'], url_path='me/stats')
    def my_grievance_stats(self, request):
        """
        GET /api/v1/school-admin/grievances/me/stats/
        Statistics for the current user's grievances.
        """
        user = request.user

        if hasattr(user, 'parentprofile'):
            student_ids = _get_parent_student_ids(user)
            qs = Grievance.objects.filter(
                Q(submitted_by=user) | Q(student_id__in=student_ids),
                school=user.school,
            ).distinct()
        else:
            qs = Grievance.objects.filter(submitted_by=user, school=user.school)

        return Response(_build_stats(qs))

    # ------------------------------------------------------------------
    # Custom actions – admin facing
    # ------------------------------------------------------------------

    @action(detail=True, methods=['post'], url_path='resolve')
    def resolve_grievance(self, request, pk=None):
        """
        POST /api/v1/school-admin/grievances/{id}/resolve/
        Mark a grievance as resolved.  Admin only (enforced by get_permissions).
        Body (optional): { "admin_remarks": "..." }
        """
        grievance = self.get_object()

        grievance.status       = Grievance.StatusChoices.RESOLVED
        grievance.admin_remarks = request.data.get('admin_remarks', grievance.admin_remarks) or ''
        grievance.resolved_at  = timezone.now()
        grievance.assigned_to  = request.user
        grievance.save(update_fields=['status', 'admin_remarks', 'resolved_at', 'assigned_to'])

        # Clear the old "new grievance" notifications (e.g. sitting in
        # other admins' bells) -- they're stale now that this is resolved --
        # then send the submitter a fresh "resolved" notification.
        self._clear_grievance_notifications(grievance)
        self._notify_submitter(grievance)

        return Response(GrievanceSerializer(grievance).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='close')
    def close_grievance(self, request, pk=None):
        """
        POST /api/v1/school-admin/grievances/{id}/close/
        Admin or the original submitter may close a grievance. Submitters
        use this endpoint to "withdraw" their own grievance.
        """
        grievance = self.get_object()
        user      = request.user

        if not (_is_school_admin(user) or grievance.submitted_by == user):
            return Response(
                {'detail': 'You are not authorised to close this grievance.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        grievance.status = Grievance.StatusChoices.CLOSED
        grievance.save(update_fields=['status'])

        # Whether an admin closed it or the submitter withdrew it, any
        # outstanding notifications about this grievance are now stale and
        # must not keep sitting in anyone's bell.
        self._clear_grievance_notifications(grievance)

        if _is_school_admin(user) and grievance.submitted_by != user:
            self._notify_submitter(grievance)

        return Response(GrievanceSerializer(grievance).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_grievance(self, request, pk=None):
        """
        POST /api/v1/school-admin/grievances/{id}/reject/
        Admin only (enforced by get_permissions).
        Body (optional): { "admin_remarks": "..." }
        """
        grievance = self.get_object()

        grievance.status        = Grievance.StatusChoices.REJECTED
        grievance.admin_remarks = request.data.get('admin_remarks', 'Grievance rejected.')
        grievance.assigned_to   = request.user
        grievance.save(update_fields=['status', 'admin_remarks', 'assigned_to'])

        self._clear_grievance_notifications(grievance)
        self._notify_submitter(grievance)

        return Response(GrievanceSerializer(grievance).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='assign')
    def assign_grievance(self, request, pk=None):
        """
        POST /api/v1/school-admin/grievances/{id}/assign/
        Admin only (enforced by get_permissions).
        Body: { "assigned_to": "<user-uuid>" }
        """
        grievance        = self.get_object()
        assigned_to_id   = request.data.get('assigned_to')

        if not assigned_to_id:
            return Response(
                {'detail': 'assigned_to is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assignee = User.objects.get(id=assigned_to_id, school=request.user.school)
        except User.DoesNotExist:
            return Response(
                {'detail': 'User not found in this school.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        grievance.assigned_to = assignee
        grievance.status      = Grievance.StatusChoices.IN_PROGRESS
        grievance.save(update_fields=['assigned_to', 'status'])

        return Response(GrievanceSerializer(grievance).data, status=status.HTTP_200_OK)

    # ------------------------------------------------------------------
    # Metadata / reference endpoints
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='categories')
    def list_categories(self, request):
        """GET /api/v1/school-admin/grievances/categories/"""
        return Response([
            {'value': 'Academic',       'label': 'Academic'},
            {'value': 'Facilities',     'label': 'Facilities'},
            {'value': 'Fee',            'label': 'Fee'},
            {'value': 'Teacher',        'label': 'Teacher'},
            {'value': 'Infrastructure', 'label': 'Infrastructure'},
            {'value': 'Transport',      'label': 'Transport'},
            {'value': 'Canteen',        'label': 'Canteen'},
            {'value': 'Examination',    'label': 'Examination'},
            {'value': 'Library',        'label': 'Library'},
            {'value': 'Sports',         'label': 'Sports'},
            {'value': 'Other',          'label': 'Other'},
        ])

    @action(detail=False, methods=['get'], url_path='priorities')
    def list_priorities(self, request):
        """GET /api/v1/school-admin/grievances/priorities/"""
        return Response([
            {'value': 'Low',    'label': 'Low',    'description': 'Minor issue, non-urgent'},
            {'value': 'Medium', 'label': 'Medium', 'description': 'Important but not critical'},
            {'value': 'High',   'label': 'High',   'description': 'Urgent, needs attention soon'},
            {'value': 'Urgent', 'label': 'Urgent', 'description': 'Critical, immediate attention required'},
        ])

    @action(detail=False, methods=['get'], url_path='admin/stats',
            permission_classes=[IsAuthenticated(), IsTeacherOrStaff()])
    def admin_stats(self, request):
        """
        GET /api/v1/school-admin/grievances/admin/stats/
        Full statistics for the admin dashboard.
        """
        grievances = Grievance.objects.filter(school=request.user.school)

        # Category breakdown
        categories = {}
        for cat in (
            grievances
            .exclude(category__isnull=True)
            .exclude(category='')
            .values_list('category', flat=True)
            .distinct()
        ):
            categories[cat] = grievances.filter(category=cat).count()

        # Last 7 days
        last_7_days = []
        for i in range(6, -1, -1):
            date  = timezone.now().date() - timezone.timedelta(days=i)
            count = grievances.filter(created_at__date=date).count()
            last_7_days.append({'date': date.isoformat(), 'count': count})

        return Response({
            **_build_stats(grievances),
            'by_category': categories,
            'by_priority': {
                'Low':    grievances.filter(priority=Grievance.PriorityChoices.LOW).count(),
                'Medium': grievances.filter(priority=Grievance.PriorityChoices.MEDIUM).count(),
                'High':   grievances.filter(priority=Grievance.PriorityChoices.HIGH).count(),
                'Urgent': grievances.filter(priority=Grievance.PriorityChoices.URGENT).count(),
            },
            'by_source': {
                'Student': grievances.filter(source_type=Grievance.SourceChoices.STUDENT).count(),
                'Parent':  grievances.filter(source_type=Grievance.SourceChoices.PARENT).count(),
            },
            'last_7_days': last_7_days,
        })


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_stats(qs) -> dict:
    """Compute standard grievance status counts from any queryset."""
    total       = qs.count()
    pending     = qs.filter(status=Grievance.StatusChoices.PENDING).count()
    in_progress = qs.filter(status=Grievance.StatusChoices.IN_PROGRESS).count()
    resolved    = qs.filter(status=Grievance.StatusChoices.RESOLVED).count()
    closed      = qs.filter(status=Grievance.StatusChoices.CLOSED).count()
    rejected    = qs.filter(status=Grievance.StatusChoices.REJECTED).count()

    return {
        'total':           total,
        'pending':         pending,
        'in_progress':     in_progress,
        'resolved':        resolved,
        'closed':          closed,
        'rejected':        rejected,
        'resolution_rate': round(resolved / total * 100, 2) if total else 0.0,
    }