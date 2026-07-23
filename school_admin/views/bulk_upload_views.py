from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django.db import transaction

from school_admin.serializers.staff_management_serializers import (
    StudentOnboardingSerializer,
    TeacherOnboardingSerializer,
    ParentOnboardingSerializer,
)
from school_admin.serializers.parent_student_mapping_serializers import (
    ParentStudentLinkSerializer,
)
from school_admin.utils.bulk_upload import parse_uploaded_file, FileParseError


class BaseBulkOnboardAPIView(generics.GenericAPIView):
    """
    Shared logic for bulk-uploading people (teachers/students/parents) via a
    CSV or XLSX file.

    Each row is validated and saved independently -- one bad row (duplicate
    email, missing field, etc.) does not block the rest of the file. The
    response reports exactly which rows succeeded and which failed, and why.

    POST body: multipart/form-data with a single field `file`.
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    serializer_class = None   # set by subclass
    role_label = "record"     # set by subclass, used in messages
    required_columns = ['first_name', 'last_name', 'email']  # override per subclass

    def row_identifier(self, row):
        """Human-readable identifier for a row, used in the success/error report.
        Override in subclasses whose rows aren't identified by an 'email' column."""
        return row.get("email")

    def post(self, request, *args, **kwargs):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {"detail": "No file uploaded. Attach a file under the 'file' field."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rows = parse_uploaded_file(uploaded_file)
        except FileParseError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if not rows:
            return Response(
                {"detail": "No data rows found in the uploaded file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        missing_columns = [c for c in self.required_columns if c not in rows[0].keys()]
        if missing_columns:
            return Response(
                {"detail": f"Missing required column(s): {', '.join(missing_columns)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []

        for index, row in enumerate(rows, start=2):  # row 1 is the header row
            identifier = self.row_identifier(row)
            serializer = self.get_serializer(data=row, context={'request': request})
            try:
                with transaction.atomic():
                    if serializer.is_valid():
                        instance = serializer.save()
                        created.append({
                            "row": index,
                            "identifier": identifier,
                            "id": str(instance.id),
                        })
                    else:
                        errors.append({
                            "row": index,
                            "identifier": identifier,
                            "errors": serializer.errors,
                        })
            except Exception as e:
                # Catches integrity errors (e.g. duplicate email) so one bad
                # row doesn't abort the whole batch.
                errors.append({
                    "row": index,
                    "identifier": identifier,
                    "errors": str(e),
                })

        return Response(
            {
                "detail": (
                    f"Processed {len(rows)} row(s): "
                    f"{len(created)} {self.role_label}(s) registered, "
                    f"{len(errors)} failed."
                ),
                "created": created,
                "errors": errors,
            },
            status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_201_CREATED,
        )


class BulkOnboardStudentAPIView(BaseBulkOnboardAPIView):
    serializer_class = StudentOnboardingSerializer
    role_label = "student"
    required_columns = ['first_name', 'last_name', 'email', 'enrollment_number']


class BulkOnboardTeacherAPIView(BaseBulkOnboardAPIView):
    serializer_class = TeacherOnboardingSerializer
    role_label = "teacher"
    required_columns = ['first_name', 'last_name', 'email', 'employee_id']


class BulkOnboardParentAPIView(BaseBulkOnboardAPIView):
    serializer_class = ParentOnboardingSerializer
    role_label = "parent"
    required_columns = ['first_name', 'last_name', 'email']


class BulkLinkParentStudentAPIView(BaseBulkOnboardAPIView):
    """
    Bulk-link existing parents to existing students via a CSV/XLSX with
    columns: parent_email, student_enrollment_number, and optionally
    relationship, is_primary_contact, can_view_academics, can_pay_fees.

    Both the parent and the student must already be registered (e.g. via
    the onboarding or bulk-onboarding endpoints) -- this endpoint only
    creates the link between them, it does not create new accounts.
    """
    serializer_class = ParentStudentLinkSerializer
    role_label = "parent-student link"
    required_columns = ['parent_email', 'student_enrollment_number']

    def row_identifier(self, row):
        return f"{row.get('parent_email')} -> {row.get('student_enrollment_number')}"