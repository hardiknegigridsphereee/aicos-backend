# notifications/serializers.py
from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """
    Read-only from the client's perspective. Notifications are only ever
    created server-side (inside the same atomic transaction as the event
    that triggers them -- see leave_management/views.py), never POSTed
    directly by the frontend.
    """
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'sender', 'sender_name', 'receiver',
            'payload', 'is_read', 'created_at',
        ]
        read_only_fields = fields

    def get_sender_name(self, obj):
        u = obj.sender
        return f"{u.first_name} {u.last_name}".strip() or u.email
