# profiles/views.py
from rest_framework import viewsets, views, response, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from tenants.views import TenantAwareModelViewSet
from accounts.permissions import IsStudent, IsTeacher, IsParent, IsParentOfStudent, IsStudentOrReadOnly
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from .serializers import (
    StudentProfileSerializer, TeacherProfileSerializer,
    ParentProfileSerializer, ParentStudentMappingSerializer
)
from academics.models import StudentEnrollment, Subject
from academics.serializers import SubjectSerializer
from operations.models import Attendance, StudentGrade, Assignment
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta


# ============================================
# STUDENT PROFILE VIEWSET - ADMIN + STUDENT
# ============================================

class StudentProfileViewSet(TenantAwareModelViewSet):
    queryset = StudentProfile.objects.select_related('user').prefetch_related(
        'parent_mappings__parent__user'
    )
    serializer_class = StudentProfileSerializer
    
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'enrollment_number', 'phone_number']
    filterset_fields = {
        'is_archived': ['exact'],
        'school': ['exact'],
    }
    
    def get_permissions(self):
        # ✅ Admin/Staff can access everything
        if self.request.user and (self.request.user.is_superuser or self.request.user.is_staff):
            return [IsAuthenticated()]
        
        # ✅ Students can access their own profile and related endpoints
        if self.action in ['retrieve', 'me', 'my_parents', 'my_subjects']:
            return [IsAuthenticated(), IsStudent()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsStudent()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset().select_related('user').prefetch_related(
            'parent_mappings__parent__user'
        )
        
        class_level = self.request.query_params.get('class_level', None)
        if class_level:
            qs = qs.filter(
                enrollments__class_level_id=class_level,
                enrollments__school=self.request.user.school
            ).distinct()
        
        user = self.request.user
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            student = StudentProfile.objects.get(user=user)
            return qs.filter(id=student.id)
        except StudentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/students/me/ - Get current student's profile
        PUT /api/v1/profiles/students/me/ - Update current student's profile
        PATCH /api/v1/profiles/students/me/ - Partial update current student's profile
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(student)
            return Response(serializer.data)
        
        serializer = self.get_serializer(student, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='me/parents')
    def my_parents(self, request):
        """
        GET /api/v1/profiles/students/me/parents/
        Returns all parents/guardians linked to the current student.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        mappings = ParentStudentMapping.objects.filter(
            student=student,
            school=request.user.school
        ).select_related('parent__user')

        data = []
        for mapping in mappings:
            data.append({
                "id": mapping.id,
                "parent_id": mapping.parent.id,
                "name": f"{mapping.parent.user.first_name} {mapping.parent.user.last_name}",
                "email": mapping.parent.user.email,
                "phone": mapping.parent.phone_number,
                "relationship": mapping.relationship,
                "is_primary_contact": mapping.is_primary_contact,
                "can_view_academics": mapping.can_view_academics,
                "can_pay_fees": mapping.can_pay_fees
            })

        return Response({"parents": data})

    @action(detail=False, methods=['get'], url_path='me/subjects')
    def my_subjects(self, request):
        """
        GET /api/v1/profiles/students/me/subjects/
        Returns all subjects for the current student's class level.
        """
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        enrollment = StudentEnrollment.objects.filter(
            student=student,
            school=request.user.school
        ).order_by('-academic_year__start_date').first()
        
        if not enrollment:
            return Response({
                "count": 0,
                "results": [],
                "detail": "No enrollment found for this student."
            }, status=status.HTTP_200_OK)
        
        subjects = Subject.objects.filter(
            class_levels=enrollment.class_level,
            school=request.user.school
        ).order_by('name')
        
        serializer = SubjectSerializer(subjects, many=True)
        return Response({
            "count": subjects.count(),
            "results": serializer.data,
            "class_level": {
                "id": str(enrollment.class_level.id),
                "name": enrollment.class_level.name
            },
            "section": {
                "id": str(enrollment.section.id),
                "name": enrollment.section.name
            },
            "academic_year": {
                "id": str(enrollment.academic_year.id),
                "name": enrollment.academic_year.name
            }
        }, status=status.HTTP_200_OK)


# ============================================
# TEACHER PROFILE VIEWSET - ADMIN + TEACHER
# ============================================

class TeacherProfileViewSet(TenantAwareModelViewSet):
    queryset = TeacherProfile.objects.select_related('user').all()
    serializer_class = TeacherProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'employee_id']
    
    def get_permissions(self):
        # ✅ Admin/Staff can access everything
        if self.request.user and (self.request.user.is_superuser or self.request.user.is_staff):
            return [IsAuthenticated()]
        
        # ✅ Teachers can access their own profile
        if self.action in ['retrieve', 'me']:
            return [IsAuthenticated(), IsTeacher()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsTeacher()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            teacher = TeacherProfile.objects.get(user=user)
            return qs.filter(id=teacher.id)
        except TeacherProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/teachers/me/ - Get current teacher's profile
        PUT /api/v1/profiles/teachers/me/ - Update current teacher's profile
        PATCH /api/v1/profiles/teachers/me/ - Partial update current teacher's profile
        """
        try:
            teacher = TeacherProfile.objects.get(user=request.user, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {"detail": "Teacher profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(teacher)
            return Response(serializer.data)
        
        serializer = self.get_serializer(teacher, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)


# ============================================
# PARENT PROFILE VIEWSET - ADMIN + PARENT
# ============================================

class ParentProfileViewSet(TenantAwareModelViewSet):
    queryset = ParentProfile.objects.select_related('user').all()
    serializer_class = ParentProfileSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['user__first_name', 'user__last_name', 'user__email', 'phone_number']
    
    def get_permissions(self):
        # ✅ Admin/Staff can access everything
        if self.request.user and (self.request.user.is_superuser or self.request.user.is_staff):
            return [IsAuthenticated()]
        
        # ✅ Parents can access their own profile and children
        if self.action in ['retrieve', 'me', 'my_children']:
            return [IsAuthenticated(), IsParent()]
        elif self.action in ['update', 'partial_update']:
            return [IsAuthenticated(), IsParent()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            parent = ParentProfile.objects.get(user=user)
            return qs.filter(id=parent.id)
        except ParentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='me')
    def me(self, request):
        """
        GET /api/v1/profiles/parents/me/ - Get current parent's profile
        PUT /api/v1/profiles/parents/me/ - Update current parent's profile
        PATCH /api/v1/profiles/parents/me/ - Partial update current parent's profile
        """
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found for this user."},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'GET':
            serializer = self.get_serializer(parent)
            return Response(serializer.data)
        
        serializer = self.get_serializer(parent, data=request.data, partial=(request.method == 'PATCH'))
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='me/children')
    def my_children(self, request):
        """
        GET /api/v1/profiles/parents/me/children/
        Returns all students linked to the current parent.
        """
        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
        except ParentProfile.DoesNotExist:
            return Response(
                {"detail": "Parent profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        mappings = ParentStudentMapping.objects.filter(
            parent=parent,
            school=request.user.school
        ).select_related('student__user', 'student')

        data = []
        for mapping in mappings:
            student = mapping.student
            enrollment = StudentEnrollment.objects.filter(
                student=student,
                school=request.user.school
            ).order_by('-academic_year__start_date').first()
            
            data.append({
                "id": mapping.id,
                "student_id": student.id,
                "name": f"{student.user.first_name} {student.user.last_name}",
                "email": student.user.email,
                "enrollment_number": student.enrollment_number,
                "relationship": mapping.relationship,
                "current_class": {
                    "class": enrollment.class_level.name if enrollment else None,
                    "section": enrollment.section.name if enrollment else None,
                    "academic_year": enrollment.academic_year.name if enrollment else None
                } if enrollment else None
            })

        return Response({"children": data})


# ============================================
# PARENT-STUDENT MAPPING VIEWSET - ADMIN + PARENT
# ============================================

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
    
    def get_permissions(self):
        # ✅ Admin/Staff can access everything
        if self.request.user and (self.request.user.is_superuser or self.request.user.is_staff):
            return [IsAuthenticated()]
        
        # ✅ Parents can access their own mappings
        if self.action in ['retrieve', 'list']:
            return [IsAuthenticated(), IsParent()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsParent()]
        elif self.action == 'request':
            return [IsAuthenticated(), IsParent()]
        else:
            return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        
        if user.is_superuser or user.is_staff:
            return qs
        
        try:
            parent = ParentProfile.objects.get(user=user)
            return qs.filter(parent=parent)
        except ParentProfile.DoesNotExist:
            return qs.none()

    @action(detail=False, methods=['post'], url_path='request')
    def request_mapping(self, request):
        """
        POST /api/v1/profiles/parent-student-mappings/request/
        Allows a parent to request linking to a student.
        """
        student_id = request.data.get('student_id')
        relationship = request.data.get('relationship', 'Guardian')
        
        if not student_id:
            return Response(
                {"detail": "student_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            parent = ParentProfile.objects.get(user=request.user, school=request.user.school)
            student = StudentProfile.objects.get(id=student_id, school=request.user.school)
        except (ParentProfile.DoesNotExist, StudentProfile.DoesNotExist):
            return Response(
                {"detail": "Invalid parent or student profile."},
                status=status.HTTP_404_NOT_FOUND
            )

        if ParentStudentMapping.objects.filter(parent=parent, student=student).exists():
            return Response(
                {"detail": "Mapping already exists."},
                status=status.HTTP_400_BAD_REQUEST
            )

        mapping = ParentStudentMapping.objects.create(
            school=request.user.school,
            parent=parent,
            student=student,
            relationship=relationship,
            is_primary_contact=False,
            can_view_academics=False,
            can_pay_fees=False
        )

        serializer = self.get_serializer(mapping)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# ============================================
# CONTEXT SWITCHING API
# ============================================

class UserContextView(views.APIView):
    """
    GET /api/v1/profiles/me/
    Returns the user's base identity, their RBAC roles, and any 
    linked profiles (Teacher, Parent, Student) for frontend context switching.
    """
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