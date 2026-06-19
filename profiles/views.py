from rest_framework import viewsets, views, response, filters
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend   # ← ADD THIS
from tenants.views import TenantAwareModelViewSet
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from .serializers import (
    StudentProfileSerializer, TeacherProfileSerializer,
    ParentProfileSerializer, ParentStudentMappingSerializer
)

class StudentProfileViewSet(TenantAwareModelViewSet):
    serializer_class = StudentProfileSerializer

    # ✅ Both SearchFilter (name/email/ID) AND DjangoFilterBackend (status/class)
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'enrollment_number', 'phone_number']
    filterset_fields = {
        'is_archived': ['exact'],           # ?is_archived=true / false
        'school': ['exact'],                # already scoped by tenant but kept for safety
    }

    def get_queryset(self):
        # Start with tenant-scoped queryset with related data prefetched
        qs = super().get_queryset().select_related('user').prefetch_related(
            'parent_mappings__parent__user'
        )
        # Handle class_level filter manually (via enrollment)
        class_level = self.request.query_params.get('class_level', None)
        if class_level:
            qs = qs.filter(
                enrollments__class_level_id=class_level,
                enrollments__school=self.request.user.school
            ).distinct()
        return qs

    # Keep the default queryset for super() to scope correctly
    queryset = StudentProfile.objects.select_related('user').prefetch_related(
        'parent_mappings__parent__user'
    ).all()


class TeacherProfileViewSet(TenantAwareModelViewSet):
    queryset = TeacherProfile.objects.select_related('user').all()
    serializer_class = TeacherProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_id']


class ParentProfileViewSet(TenantAwareModelViewSet):
    queryset = ParentProfile.objects.select_related('user').all()
    serializer_class = ParentProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone_number']


class ParentStudentMappingViewSet(TenantAwareModelViewSet):
    queryset = ParentStudentMapping.objects.all()
    serializer_class = ParentStudentMappingSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'parent__user__first_name',
        'parent__user__last_name',
        'student__user__first_name',
        'student__user__last_name',
        'relationship'
    ]


class UserContextView(views.APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        student_profile = StudentProfile.objects.filter(user=user).first()
        teacher_profile = TeacherProfile.objects.filter(user=user).first()
        parent_profile = ParentProfile.objects.filter(user=user).first()

        roles = []
        if hasattr(user, 'user_roles'):
            roles = list(user.user_roles.filter(school=user.school).values_list('role__name', flat=True))

        payload = {
            "identity": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "school_id": user.school_id,
            },
            "roles": roles,
            "is_superuser": user.is_superuser,
            "profiles": {
                "student": {"exists": bool(student_profile), "id": student_profile.id if student_profile else None},
                "teacher": {"exists": bool(teacher_profile), "id": teacher_profile.id if teacher_profile else None},
                "parent":  {"exists": bool(parent_profile),  "id": parent_profile.id  if parent_profile  else None},
            }
        }
        return response.Response(payload)