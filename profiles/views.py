from rest_framework import viewsets, views, response, filters
from rest_framework.permissions import IsAuthenticated
from tenants.views import TenantAwareModelViewSet
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from .serializers import (
    StudentProfileSerializer, TeacherProfileSerializer, 
    ParentProfileSerializer, ParentStudentMappingSerializer
)

# --- TASK 2.3: Profile APIs ---

class StudentProfileViewSet(TenantAwareModelViewSet):
    queryset = StudentProfile.objects.all()
    serializer_class = StudentProfileSerializer
    
    filter_backends = [filters.SearchFilter]
    # FIXED: Added 'user__' to traverse the OneToOne relationship
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'enrollment_number']

class TeacherProfileViewSet(TenantAwareModelViewSet):
    queryset = TeacherProfile.objects.all()
    serializer_class = TeacherProfileSerializer
    
    filter_backends = [filters.SearchFilter]
    # FIXED: Added 'user__'
    search_fields = ['user__first_name', 'user__last_name', 'user__email']

class ParentProfileViewSet(TenantAwareModelViewSet):
    queryset = ParentProfile.objects.all()
    serializer_class = ParentProfileSerializer
    
    filter_backends = [filters.SearchFilter]
    # FIXED: Added 'user__' (phone_number belongs to the profile, so it stays as is)
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone_number']

class ParentStudentMappingViewSet(TenantAwareModelViewSet):
    queryset = ParentStudentMapping.objects.all()
    serializer_class = ParentStudentMappingSerializer

    # --- ADDED FOR SEARCH FUNCTIONALITY ---
    filter_backends = [filters.SearchFilter]
    search_fields = [
        'parent__user__first_name', 
        'parent__user__last_name', 
        'student__user__first_name', 
        'student__user__last_name',
        'relationship' # FIXED: Changed from 'relationship_type' to 'relationship'
    ]

# --- TASK 2.4: Context Switching API ---

class UserContextView(views.APIView):
    """
    GET /api/v1/profiles/me/
    Returns the user's base identity, their RBAC roles, and any 
    linked profiles (Teacher, Parent, Student) for frontend context switching.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        
        # 1. Fetch any linked profiles for this user
        student_profile = StudentProfile.objects.filter(user=user).first()
        teacher_profile = TeacherProfile.objects.filter(user=user).first()
        parent_profile = ParentProfile.objects.filter(user=user).first()

        # 2. Fetch active roles from the RBAC engine (Accounts App)
        # Using a safe fallback in case user_roles isn't defined properly yet
        roles = []
        if hasattr(user, 'user_roles'):
            roles = list(user.user_roles.filter(school=user.school).values_list('role__name', flat=True))

        # 3. Construct the Context Payload
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
                "student": {
                    "exists": bool(student_profile),
                    "id": student_profile.id if student_profile else None,
                },
                "teacher": {
                    "exists": bool(teacher_profile),
                    "id": teacher_profile.id if teacher_profile else None,
                },
                "parent": {
                    "exists": bool(parent_profile),
                    "id": parent_profile.id if parent_profile else None,
                }
            }
        }
        
        return response.Response(payload)