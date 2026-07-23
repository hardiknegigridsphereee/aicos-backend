# school_admin/utils/email.py
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

ROLE_LABELS = {
    'teacher': 'Teacher',
    'student': 'Student',
    'parent': 'Parent',
}


def send_registration_email(user, role, temporary_password):
    """
    Sends a welcome email with login credentials to a newly onboarded
    teacher/student/parent.

    Failures are logged, not raised -- a broken mail server or bad SMTP
    config should never block account creation. This matters especially
    for bulk uploads, where one email failure must not sink an otherwise
    successful row (or the whole batch).
    """
    role_label = ROLE_LABELS.get(role, 'User')
    school_name = getattr(user.school, 'name', 'your school')

    subject = f"Welcome to {school_name} - Your {role_label} Account"
    message = (
        f"Hello {user.first_name},\n\n"
        f"An account has been created for you at {school_name} as a {role_label}.\n\n"
        f"Login email: {user.email}\n"
        f"Temporary password: {temporary_password}\n\n"
        f"Please log in and change your password as soon as possible.\n\n"
        f"- {school_name} Administration"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send registration email to %s (role=%s)", user.email, role
        )