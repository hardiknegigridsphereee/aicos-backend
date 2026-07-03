# profiles/views.py
from rest_framework import viewsets, views, response, filters, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from tenants.views import TenantAwareModelViewSet
from accounts.permissions import IsStudent, IsTeacher, IsParent, IsParentOfStudent, IsStudentOrReadOnly, IsTeacherOrStaff
from .models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping, StudentDevice, StudentLocationHistory
from .serializers import (
    StudentProfileSerializer, TeacherProfileSerializer,
    ParentProfileSerializer, ParentStudentMappingSerializer,
    # Location serializers
    StudentDeviceSerializer,
    StudentLocationHistorySerializer,
    StudentLocationUpdateSerializer,
    StudentDeviceCreateSerializer,
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


# ============================================================
# LOCATION VIEWS (NEW)
# ============================================================

class StudentDeviceDetailView(views.APIView):
    """
    GET /api/v1/profiles/students/me/device/ - Get current student's device
    POST /api/v1/profiles/students/me/device/ - Create or update device
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
            device = StudentDevice.objects.get(student=student)
            serializer = StudentDeviceSerializer(device)
            return Response(serializer.data)
        except StudentProfile.DoesNotExist:
            return Response(
                {'detail': 'Student profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        except StudentDevice.DoesNotExist:
            return Response(
                {'detail': 'No device registered for this student.'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def post(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {'detail': 'Student profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if device already exists
        existing = StudentDevice.objects.filter(student=student).first()
        if existing:
            # Update existing device
            serializer = StudentDeviceSerializer(existing, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Create new device
        serializer = StudentDeviceCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            device = serializer.save(school=request.user.school)
            return Response(
                StudentDeviceSerializer(device).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentDeviceUpdateView(views.APIView):
    """
    PUT/PATCH /api/v1/profiles/students/me/device/update/
    Update current student's device info
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def patch(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
            device = StudentDevice.objects.get(student=student)
        except (StudentProfile.DoesNotExist, StudentDevice.DoesNotExist):
            return Response(
                {'detail': 'Student or device not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = StudentDeviceSerializer(device, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentUpdateLocationView(views.APIView):
    """
    POST /api/v1/profiles/students/me/location/update/
    Update current student's location (from device)
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def post(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
            device = StudentDevice.objects.get(student=student)
        except (StudentProfile.DoesNotExist, StudentDevice.DoesNotExist):
            return Response(
                {'detail': 'Student or device not found. Please register your device first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = StudentLocationUpdateSerializer(data=request.data)
        if serializer.is_valid():
            location_data = serializer.validated_data
            
            # Update device location
            history = device.update_location(
                latitude=location_data['latitude'],
                longitude=location_data['longitude'],
                location_time=location_data.get('location_time'),
                accuracy=location_data.get('accuracy'),
                altitude=location_data.get('altitude'),
                speed=location_data.get('speed'),
                heading=location_data.get('heading'),
            )
            
            return Response({
                'detail': 'Location updated successfully.',
                'location': StudentLocationHistorySerializer(history).data,
                'device': StudentDeviceSerializer(device).data,
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentLocationHistoryView(views.APIView):
    """
    GET /api/v1/profiles/students/me/location/history/
    Get location history for current student
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {'detail': 'Student profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get query params
        days = request.query_params.get('days', 7)
        limit = request.query_params.get('limit', 50)
        
        try:
            days = int(days)
            limit = int(limit)
        except ValueError:
            days = 7
            limit = 50
        
        history = student.get_location_history(days=days)[:limit]
        serializer = StudentLocationHistorySerializer(history, many=True)
        
        return Response({
            'count': history.count(),
            'days': days,
            'limit': limit,
            'results': serializer.data
        })


class StudentLocationAdminView(views.APIView):
    """
    GET /api/v1/profiles/locations/students/{student_id}/
    Get location for a specific student (Admin/Staff only)
    """
    permission_classes = [IsAuthenticated, IsTeacherOrStaff]
    
    def get(self, request, student_id):
        try:
            student = StudentProfile.objects.get(id=student_id, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {'detail': 'Student not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            device = StudentDevice.objects.get(student=student)
            device_serializer = StudentDeviceSerializer(device)
            
            # Get recent history
            history = student.location_history.all().order_by('-location_time')[:10]
            history_serializer = StudentLocationHistorySerializer(history, many=True)
            
            return Response({
                'student': {
                    'id': str(student.id),
                    'name': f"{student.user.first_name} {student.user.last_name}",
                    'enrollment_number': student.enrollment_number,
                },
                'device': device_serializer.data,
                'recent_history': history_serializer.data,
            })
        except StudentDevice.DoesNotExist:
            return Response({
                'student': {
                    'id': str(student.id),
                    'name': f"{student.user.first_name} {student.user.last_name}",
                    'enrollment_number': student.enrollment_number,
                },
                'device': None,
                'recent_history': [],
                'detail': 'No device registered for this student.'
            })


class ParentChildLocationView(views.APIView):
    """
    GET /api/v1/profiles/parents/me/children/{child_id}/location/
    Get location for a specific child (Parent only)
    """
    permission_classes = [IsAuthenticated, IsParent]
    
    def get(self, request, child_id):
        try:
            parent = request.user.parentprofile
        except ParentProfile.DoesNotExist:
            return Response(
                {'detail': 'Parent profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify parent-child relationship
        try:
            mapping = ParentStudentMapping.objects.get(
                parent=parent,
                student_id=child_id,
                school=request.user.school,
                can_view_academics=True
            )
        except ParentStudentMapping.DoesNotExist:
            return Response(
                {'detail': 'You are not authorized to view this child\'s location.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        student = mapping.student
        
        try:
            device = StudentDevice.objects.get(student=student)
            
            # Get location history (last 24 hours)
            from django.utils import timezone
            from datetime import timedelta
            cutoff = timezone.now() - timedelta(hours=24)
            history = student.location_history.filter(
                location_time__gte=cutoff
            ).order_by('-location_time')[:20]
            
            return Response({
                'child': {
                    'id': str(student.id),
                    'name': f"{student.user.first_name} {student.user.last_name}",
                    'enrollment_number': student.enrollment_number,
                    'relationship': mapping.relationship,
                },
                'current_location': {
                    'latitude': float(device.last_latitude) if device.last_latitude else None,
                    'longitude': float(device.last_longitude) if device.last_longitude else None,
                    'timestamp': device.last_location_update,
                    'accuracy': None,
                } if device.last_latitude else None,
                'device_info': {
                    'device_name': device.device_name,
                    'device_type': device.get_device_type_display(),
                    'is_active': device.is_active,
                    'last_updated': device.last_location_update,
                },
                'recent_history': StudentLocationHistorySerializer(history, many=True).data,
            })
        except StudentDevice.DoesNotExist:
            return Response({
                'child': {
                    'id': str(student.id),
                    'name': f"{student.user.first_name} {student.user.last_name}",
                    'enrollment_number': student.enrollment_number,
                },
                'current_location': None,
                'device_info': None,
                'recent_history': [],
                'detail': 'No device registered for this child.'
            })


class ParentChildrenLocationsView(views.APIView):
    """
    GET /api/v1/profiles/parents/me/children/locations/
    Get locations for all children (Parent only)
    """
    permission_classes = [IsAuthenticated, IsParent]
    
    def get(self, request):
        try:
            parent = request.user.parentprofile
        except ParentProfile.DoesNotExist:
            return Response(
                {'detail': 'Parent profile not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all children
        mappings = ParentStudentMapping.objects.filter(
            parent=parent,
            school=request.user.school,
            can_view_academics=True
        ).select_related('student__user')
        
        children_data = []
        for mapping in mappings:
            student = mapping.student
            device = StudentDevice.objects.filter(student=student).first()
            
            child_info = {
                'id': str(student.id),
                'name': f"{student.user.first_name} {student.user.last_name}",
                'enrollment_number': student.enrollment_number,
                'relationship': mapping.relationship,
                'has_device': bool(device),
                'last_location': None,
                'device_info': None,
            }
            
            if device:
                child_info['last_location'] = {
                    'latitude': float(device.last_latitude) if device.last_latitude else None,
                    'longitude': float(device.last_longitude) if device.last_longitude else None,
                    'timestamp': device.last_location_update,
                }
                child_info['device_info'] = {
                    'device_name': device.device_name,
                    'device_type': device.get_device_type_display(),
                    'is_active': device.is_active,
                    'last_updated': device.last_location_update,
                }
            
            children_data.append(child_info)
        
        return Response({
            'count': len(children_data),
            'children': children_data
        })