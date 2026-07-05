from django.conf import settings
from django.db import models

from tenants.models import TenantAwareModel


class Notification(TenantAwareModel):
    """
    Generic, directed (sender -> receiver) notification. Used for leave
    request events today; `notification_type` + `payload` make it reusable
    for circulars, grievances, etc. without schema changes.

    `id` is a plain BigAutoField (DEFAULT_AUTO_FIELD in settings) -- it does
    NOT need to match the UUID pk of User, LeaveRequest, etc. `payload` is
    where those foreign ids/metadata live instead.
    """

    class NotificationType(models.TextChoices):
        LEAVE = 'leave', 'Leave'
        CIRCULAR = 'circular', 'Circular'
        GRIEVANCE = 'grievance', 'Grievance'

    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_notifications',
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_notifications',
    )

    # Dynamic metadata: e.g. {"leave_id": "...", "leave_type": "Sick",
    # "status": "Pending", "start_date": "...", "end_date": "...",
    # "applicant_name": "...", "redirect_module": "leave-dashboard"}
    payload = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['receiver', 'is_read'], name='notif_receiver_isread_idx'),
            models.Index(fields=['receiver', 'notification_type'], name='notif_receiver_type_idx'),
        ]

    def __str__(self):
        state = 'read' if self.is_read else 'unread'
        return f"[{self.notification_type}] {self.sender_id} -> {self.receiver_id} ({state})"
