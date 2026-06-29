import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.local")  # or .prod, whichever you're running
django.setup()

from django.db import transaction
from tenants.models import User, School
from profiles.models import StudentProfile, ParentProfile, ParentStudentMapping

CHILD_USER_ID = "d3f55494-9ec1-41fd-9bcc-23af15cf1049"

# --- Fill these in for the parent ---
PARENT_EMAIL = "parent@example.com"
PARENT_FIRST_NAME = "john"
PARENT_LAST_NAME = "wick"
PARENT_PASSWORD = "parent@1234"
RELATIONSHIP = "Mother"  # or "Father", "Guardian" etc.

with transaction.atomic():
    student_profile = StudentProfile.objects.get(user__id=CHILD_USER_ID)
    school = student_profile.school

    parent_user = User.objects.create_user(
        email=PARENT_EMAIL,
        password=PARENT_PASSWORD,
        first_name=PARENT_FIRST_NAME,
        last_name=PARENT_LAST_NAME,
        school=school,
    )

    parent_profile = ParentProfile.objects.create(
        user=parent_user,
        school=school,
    )

    mapping = ParentStudentMapping.objects.create(
        school=school,
        parent=parent_profile,
        student=student_profile,
        relationship=RELATIONSHIP,
        is_primary_contact=True,
        can_view_academics=True,
        can_pay_fees=True,
    )

    print(f"Parent created: {parent_user.email} (id={parent_user.id})")
    print(f"Parent profile id: {parent_profile.id}")
    print(f"Mapping id: {mapping.id} -> linked to student {student_profile.user.email}")