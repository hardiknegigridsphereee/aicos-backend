# notifications/views.py
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import mixins, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET  /api/v1/notifications/                 -> notifications addressed to *me* (newest first)
    GET  /api/v1/notifications/{id}/             -> retrieve one
    GET  /api/v1/notifications/unread-count/     -> {"unread_count": N}   (poll this cheaply)
    POST /api/v1/notifications/{id}/mark-read/   -> marks it read, returns it
    POST /api/v1/notifications/mark-all-read/    -> marks every unread notification of mine as read

    Query params on list/unread-count:
      ?is_read=true|false
      ?notification_type=leave|circular|grievance
    """
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['is_read', 'notification_type']
    ordering = ['-created_at']

    def get_queryset(self):
        # A notification is only ever visible to the user it was addressed to.
        return Notification.objects.filter(receiver=self.request.user).select_related('sender')

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'unread_count': count})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        """
        Call this when the notification is clicked, then use
        `payload.redirect_module` (+ `payload.leave_id`) from the response
        to route the user to the right panel.
        """
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=['is_read'])
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'marked_read': updated}, status=status.HTTP_200_OK)
