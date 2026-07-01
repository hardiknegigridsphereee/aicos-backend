# timetable/views.py
from rest_framework import status, filters
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from academics.models import AcademicYear, ClassLevel, Section, Subject, StudentEnrollment
from profiles.models import StudentProfile, TeacherProfile, ParentProfile, ParentStudentMapping
from school_admin.models import TimetableSettings

from .models import TimeSlot, TimetableEntry, TimetableTemplate
from .serializers import (
    TimeSlotSerializer, TimeSlotCreateSerializer,
    TimetableEntrySerializer, TimetableEntryCreateSerializer,
    TimetableEntryUpdateSerializer, TimetableEntryBulkCreateSerializer,
    TimetableTemplateSerializer, TimetableSummarySerializer,
)
from .permissions import IsSchoolAdminOrStaff, IsStudentOrTeacher, is_school_admin
from .utils import (
    get_student_current_section, get_teacher_sections,
    get_student_timetable, get_teacher_timetable,
    get_section_timetable, get_class_timetable,
    check_conflicts, organize_timetable_by_day,
    generate_time_slots_from_settings
)


# ---------------------------------------------------------------------------
# TimeSlot ViewSet
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="List all time slots"),
    create=extend_schema(summary="Create a new time slot"),
    retrieve=extend_schema(summary="Get time slot details"),
    update=extend_schema(summary="Update a time slot"),
    partial_update=extend_schema(summary="Partially update a time slot"),
    destroy=extend_schema(summary="Delete a time slot"),
)
class TimeSlotViewSet(TenantAwareModelViewSet):
    """
    Manage time slots for the school timetable.
    """
    queryset = TimeSlot.objects.select_related('academic_year').all()
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['day', 'is_break', 'academic_year']
    search_fields = ['day', 'break_name']
    ordering_fields = ['day', 'period_number', 'start_time']
    ordering = ['day', 'period_number']

    def get_serializer_class(self):
        if self.action == 'create':
            return TimeSlotCreateSerializer
        return TimeSlotSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsSchoolAdminOrStaff()]

    def perform_create(self, serializer):
        serializer.save(school=self.request.user.school)


# ---------------------------------------------------------------------------
# TimetableEntry ViewSet
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="List timetable entries"),
    create=extend_schema(summary="Create a new timetable entry"),
    retrieve=extend_schema(summary="Get timetable entry details"),
    update=extend_schema(summary="Update a timetable entry"),
    partial_update=extend_schema(summary="Partially update a timetable entry"),
    destroy=extend_schema(summary="Delete a timetable entry"),
)
class TimetableEntryViewSet(TenantAwareModelViewSet):
    """
    Manage timetable entries.
    
    - Students: Can view their own class timetable
    - Teachers: Can view timetables for classes they teach
    - Parents: Can view timetables for their children (via my-timetable with ?student_id)
    - Admins: Full CRUD access
    """
    queryset = TimetableEntry.objects.select_related(
        'class_level', 'section', 'subject', 'teacher__user', 'time_slot', 'academic_year'
    ).all()
    
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        'class_level': ['exact'],
        'section': ['exact'],
        'subject': ['exact'],
        'teacher': ['exact'],
        'academic_year': ['exact'],
        'is_active': ['exact'],
        'time_slot__day': ['exact'],
    }
    search_fields = [
        'room_number', 'notes',
        'class_level__name', 'section__name', 'subject__name',
        'teacher__user__first_name', 'teacher__user__last_name',
    ]
    ordering_fields = ['class_level__numeric_order', 'section__name', 'time_slot__day', 'time_slot__period_number']
    ordering = ['class_level__numeric_order', 'section__name', 'time_slot__day', 'time_slot__period_number']

    def get_serializer_class(self):
        if self.action == 'create':
            return TimetableEntryCreateSerializer
        if self.action in ['update', 'partial_update']:
            return TimetableEntryUpdateSerializer
        return TimetableEntrySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAuthenticated()]
        elif self.action in ['generate_slots', 'bulk_create']:
            return [IsAuthenticated(), IsSchoolAdminOrStaff()]
        elif self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAuthenticated(), IsSchoolAdminOrStaff()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        
        # Admin/Staff can see everything
        if user.is_superuser or user.is_staff or is_school_admin(user):
            return qs
        
        # Students can see their own class timetable
        if hasattr(user, 'studentprofile'):
            student = user.studentprofile
            section, academic_year = get_student_current_section(student)
            if section and academic_year:
                return qs.filter(section=section, academic_year=academic_year, is_active=True)
            return qs.none()
        
        # Teachers can see timetables for classes they teach
        if hasattr(user, 'teacherprofile'):
            teacher = user.teacherprofile
            sections = get_teacher_sections(teacher)
            return qs.filter(section__in=sections, is_active=True)
        
        # Fallback: no access
        return qs.none()

    def perform_create(self, serializer):
        serializer.save(
            school=self.request.user.school,
            created_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save()

    # ------------------------------------------------------------------
    # Generate time slots from settings
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='generate-slots')
    def generate_slots(self, request):
        """
        POST /api/v1/timetable/entries/generate-slots/
        Generate time slots from timetable settings for an academic year.
        
        Body: { "academic_year_id": "uuid" }
        """
        academic_year_id = request.data.get('academic_year_id')
        
        if not academic_year_id:
            return Response(
                {'detail': 'academic_year_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            settings = TimetableSettings.objects.get(school=request.user.school)
        except TimetableSettings.DoesNotExist:
            return Response(
                {'detail': 'Timetable settings not configured. Please complete onboarding first.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Delete existing time slots for this academic year
        TimeSlot.objects.filter(school=request.user.school, academic_year=academic_year).delete()
        
        # Generate new time slots
        time_slots = generate_time_slots_from_settings(settings, academic_year)
        
        try:
            with transaction.atomic():
                created = TimeSlot.objects.bulk_create(time_slots)
                serializer = TimeSlotSerializer(created, many=True)
                return Response({
                    'detail': f'Successfully generated {len(created)} time slots.',
                    'slots': serializer.data
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'detail': f'Failed to generate time slots: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Bulk create entries
    # ------------------------------------------------------------------

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        """
        POST /api/v1/timetable/entries/bulk-create/
        Create multiple timetable entries at once.
        """
        serializer = TimetableEntryBulkCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        academic_year_id = serializer.validated_data['academic_year_id']
        entries_data = serializer.validated_data['entries']
        school = request.user.school
        
        entries_to_create = []
        for entry_data in entries_data:
            entries_to_create.append(
                TimetableEntry(
                    school=school,
                    created_by=request.user,
                    academic_year_id=academic_year_id,
                    **entry_data
                )
            )
        
        try:
            with transaction.atomic():
                created = TimetableEntry.objects.bulk_create(entries_to_create)
                response_serializer = TimetableEntrySerializer(created, many=True)
                return Response({
                    'detail': f'Successfully created {len(created)} timetable entries.',
                    'entries': response_serializer.data
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'detail': f'Failed to create entries: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Summary endpoint
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        GET /api/v1/timetable/entries/summary/
        Returns a summary of the timetable for the current academic year.
        """
        academic_year_id = request.query_params.get('academic_year')
        
        try:
            if academic_year_id:
                academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
            else:
                academic_year = AcademicYear.objects.filter(
                    school=request.user.school,
                    is_active=True
                ).first()
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not academic_year:
            return Response(
                {'detail': 'No academic year found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            settings = TimetableSettings.objects.get(school=request.user.school)
        except TimetableSettings.DoesNotExist:
            return Response({
                'settings_exist': False,
                'detail': 'Timetable settings not configured.'
            }, status=status.HTTP_200_OK)
        
        entries_count = TimetableEntry.objects.filter(
            school=request.user.school,
            academic_year=academic_year,
            is_active=True
        ).count()
        
        return Response({
            'settings_exist': True,
            'total_entries': entries_count,
            'academic_year': academic_year.name,
            'working_days': settings.get_working_days_list(),
            'periods_per_day': settings.periods_per_day,
            'period_times': settings.get_period_times()
        })

    # ------------------------------------------------------------------
    # My Timetable (Student/Teacher/Parent)
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='my-timetable')
    def my_timetable(self, request):
        """
        GET /api/v1/timetable/entries/my-timetable/
        Returns the timetable for:
        - Students: Their own timetable (auto-detected)
        - Teachers: Their own timetable (auto-detected, can filter by academic_year)
        - Parents: Their child's timetable (requires ?student_id=UUID)
        
        Query params:
        - academic_year: UUID (optional) - For teachers/parents to specify year
        - student_id: UUID (required for parents) - The child's student ID
        
        Returns: Formatted timetable by day and period
        """
        user = request.user
        student_id = request.query_params.get('student_id')
        academic_year_id = request.query_params.get('academic_year')
        
        # ── PARENT VIEW ──────────────────────────────────────────────────────
        # Check if user is a parent and wants to view a child's timetable
        if hasattr(user, 'parentprofile') and student_id:
            parent = user.parentprofile
            
            # Verify parent-child relationship
            try:
                mapping = ParentStudentMapping.objects.get(
                    parent=parent,
                    student_id=student_id,
                    school=user.school,
                    can_view_academics=True
                )
            except ParentStudentMapping.DoesNotExist:
                return Response(
                    {'detail': 'You are not authorized to view this student\'s timetable.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            student = mapping.student
            
            # Get the academic year from enrollment or query param
            enrollment = StudentEnrollment.objects.filter(
                student=student,
                school=user.school
            ).order_by('-academic_year__start_date').first()
            
            if not enrollment:
                return Response(
                    {'detail': 'Student is not enrolled in any academic year.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Use provided academic_year or fallback to enrollment's year
            if academic_year_id:
                try:
                    academic_year = AcademicYear.objects.get(
                        id=academic_year_id,
                        school=user.school
                    )
                except AcademicYear.DoesNotExist:
                    return Response(
                        {'detail': 'Academic year not found.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            else:
                academic_year = enrollment.academic_year
            
            # Get timetable for this student's section and academic year
            entries = get_student_timetable(student, academic_year)
            timetable = organize_timetable_by_day(entries)
            
            section = enrollment.section
            
            # Format the timetable for display
            formatted_timetable = {}
            for day, periods in timetable.items():
                formatted_timetable[day] = {}
                for period, entry in periods.items():
                    if entry:
                        formatted_timetable[day][period] = {
                            'id': str(entry.id),
                            'subject': entry.subject.name,
                            'teacher': f"{entry.teacher.user.first_name} {entry.teacher.user.last_name}",
                            'room': entry.room_number,
                            'notes': entry.notes,
                            'subject_id': str(entry.subject.id),
                            'teacher_id': str(entry.teacher.id),
                            'time_slot': {
                                'start_time': entry.time_slot.start_time.strftime('%H:%M'),
                                'end_time': entry.time_slot.end_time.strftime('%H:%M'),
                            }
                        }
            
            return Response({
                'user_type': 'parent',
                'parent_name': f"{parent.user.first_name} {parent.user.last_name}",
                'student_name': f"{student.user.first_name} {student.user.last_name}",
                'student_id': str(student.id),
                'class_level': section.class_level.name if section else None,
                'section': section.name if section else None,
                'academic_year': academic_year.name,
                'timetable': formatted_timetable
            })
        
        # ── PARENT WITH NO STUDENT_ID ──────────────────────────────────────
        # Parent didn't specify student_id - return list of their children
        if hasattr(user, 'parentprofile'):
            parent = user.parentprofile
            children_mappings = ParentStudentMapping.objects.filter(
                parent=parent,
                school=user.school,
                can_view_academics=True
            ).select_related('student__user')
            
            if not children_mappings.exists():
                return Response({
                    'user_type': 'parent',
                    'parent_name': f"{parent.user.first_name} {parent.user.last_name}",
                    'message': 'No children found with academic access.',
                    'children': []
                })
            
            children_data = []
            for mapping in children_mappings:
                student = mapping.student
                enrollment = StudentEnrollment.objects.filter(
                    student=student,
                    school=user.school
                ).order_by('-academic_year__start_date').first()
                
                children_data.append({
                    'id': str(student.id),
                    'name': f"{student.user.first_name} {student.user.last_name}",
                    'enrollment_number': student.enrollment_number,
                    'relationship': mapping.relationship,
                    'current_class': {
                        'class': enrollment.class_level.name if enrollment else None,
                        'section': enrollment.section.name if enrollment else None,
                        'academic_year': enrollment.academic_year.name if enrollment else None
                    } if enrollment else None
                })
            
            return Response({
                'user_type': 'parent',
                'parent_name': f"{parent.user.first_name} {parent.user.last_name}",
                'message': 'Please specify ?student_id=UUID to view a child\'s timetable.',
                'children': children_data
            })
        
        # ── STUDENT VIEW ────────────────────────────────────────────────────
        # Student viewing their own timetable
        if hasattr(user, 'studentprofile'):
            student = user.studentprofile
            
            # Get the student's current enrollment
            enrollment = StudentEnrollment.objects.filter(
                student=student,
                school=user.school
            ).order_by('-academic_year__start_date').first()
            
            if not enrollment:
                return Response(
                    {'detail': 'Student is not enrolled in any academic year.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Use the enrollment's academic year
            academic_year = enrollment.academic_year
            
            # Get timetable for this student's section and academic year
            entries = get_student_timetable(student, academic_year)
            timetable = organize_timetable_by_day(entries)
            
            section = enrollment.section
            
            # Format the timetable for display
            formatted_timetable = {}
            for day, periods in timetable.items():
                formatted_timetable[day] = {}
                for period, entry in periods.items():
                    if entry:
                        formatted_timetable[day][period] = {
                            'id': str(entry.id),
                            'subject': entry.subject.name,
                            'teacher': f"{entry.teacher.user.first_name} {entry.teacher.user.last_name}",
                            'room': entry.room_number,
                            'notes': entry.notes,
                            'subject_id': str(entry.subject.id),
                            'teacher_id': str(entry.teacher.id),
                            'time_slot': {
                                'start_time': entry.time_slot.start_time.strftime('%H:%M'),
                                'end_time': entry.time_slot.end_time.strftime('%H:%M'),
                            }
                        }
            
            return Response({
                'user_type': 'student',
                'student_name': f"{student.user.first_name} {student.user.last_name}",
                'class_level': section.class_level.name if section else None,
                'section': section.name if section else None,
                'academic_year': academic_year.name,
                'timetable': formatted_timetable
            })
        
        # ── TEACHER VIEW ────────────────────────────────────────────────────
        if hasattr(user, 'teacherprofile'):
            teacher = user.teacherprofile
            
            # Allow optional academic_year query param for teachers
            try:
                if academic_year_id:
                    academic_year = AcademicYear.objects.get(id=academic_year_id, school=user.school)
                else:
                    # For teachers, use active academic year if not specified
                    academic_year = AcademicYear.objects.filter(
                        school=user.school,
                        is_active=True
                    ).first()
            except AcademicYear.DoesNotExist:
                return Response(
                    {'detail': 'Academic year not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            if not academic_year:
                return Response(
                    {'detail': 'No academic year specified.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            entries = get_teacher_timetable(teacher, academic_year)
            timetable = organize_timetable_by_day(entries)
            
            # Format the timetable for display
            formatted_timetable = {}
            for day, periods in timetable.items():
                formatted_timetable[day] = {}
                for period, entry in periods.items():
                    if entry:
                        formatted_timetable[day][period] = {
                            'id': str(entry.id),
                            'class_level': entry.class_level.name,
                            'section': entry.section.name,
                            'subject': entry.subject.name,
                            'room': entry.room_number,
                            'notes': entry.notes,
                            'class_level_id': str(entry.class_level.id),
                            'section_id': str(entry.section.id),
                            'subject_id': str(entry.subject.id),
                            'time_slot': {
                                'start_time': entry.time_slot.start_time.strftime('%H:%M'),
                                'end_time': entry.time_slot.end_time.strftime('%H:%M'),
                            }
                        }
            
            return Response({
                'user_type': 'teacher',
                'teacher_name': f"{teacher.user.first_name} {teacher.user.last_name}",
                'academic_year': academic_year.name,
                'timetable': formatted_timetable
            })
        
        return Response(
            {'detail': 'Only students, teachers, and parents can view timetables.'},
            status=status.HTTP_403_FORBIDDEN
        )

    # ------------------------------------------------------------------
    # Section Timetable
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='section/(?P<section_id>[^/.]+)')
    def section_timetable(self, request, section_id):
        """
        GET /api/v1/timetable/entries/section/{section_id}/
        Returns the timetable for a specific section.
        """
        try:
            section = Section.objects.get(id=section_id, school=request.user.school)
        except Section.DoesNotExist:
            return Response(
                {'detail': 'Section not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        academic_year_id = request.query_params.get('academic_year')
        try:
            if academic_year_id:
                academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
            else:
                academic_year = AcademicYear.objects.filter(
                    school=request.user.school,
                    is_active=True
                ).first()
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not academic_year:
            return Response(
                {'detail': 'Academic year not specified.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entries = get_section_timetable(section, academic_year)
        timetable = organize_timetable_by_day(entries)
        
        # Format the timetable
        formatted_timetable = {}
        for day, periods in timetable.items():
            formatted_timetable[day] = {}
            for period, entry in periods.items():
                if entry:
                    formatted_timetable[day][period] = {
                        'id': str(entry.id),
                        'subject': entry.subject.name,
                        'teacher': f"{entry.teacher.user.first_name} {entry.teacher.user.last_name}",
                        'room': entry.room_number,
                        'notes': entry.notes,
                        'subject_id': str(entry.subject.id),
                        'teacher_id': str(entry.teacher.id),
                    }
        
        return Response({
            'section': {
                'id': str(section.id),
                'name': section.name,
                'class_level': section.class_level.name,
                'class_level_id': str(section.class_level.id),
            },
            'academic_year': academic_year.name,
            'timetable': formatted_timetable
        })

    # ------------------------------------------------------------------
    # Class Timetable (all sections of a class)
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='class/(?P<class_level_id>[^/.]+)')
    def class_timetable(self, request, class_level_id):
        """
        GET /api/v1/timetable/entries/class/{class_level_id}/
        Returns the timetable for all sections of a class level.
        """
        try:
            class_level = ClassLevel.objects.get(id=class_level_id, school=request.user.school)
        except ClassLevel.DoesNotExist:
            return Response(
                {'detail': 'Class level not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        academic_year_id = request.query_params.get('academic_year')
        try:
            if academic_year_id:
                academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
            else:
                academic_year = AcademicYear.objects.filter(
                    school=request.user.school,
                    is_active=True
                ).first()
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not academic_year:
            return Response(
                {'detail': 'Academic year not specified.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entries = get_class_timetable(class_level, academic_year)
        
        # Group by section
        sections_data = {}
        for entry in entries:
            section_name = entry.section.name
            if section_name not in sections_data:
                sections_data[section_name] = {
                    'section_id': str(entry.section.id),
                    'section_name': section_name,
                    'timetable': {}
                }
            
            day = entry.time_slot.day
            period = entry.time_slot.period_number
            if day not in sections_data[section_name]['timetable']:
                sections_data[section_name]['timetable'][day] = {}
            
            sections_data[section_name]['timetable'][day][period] = {
                'id': str(entry.id),
                'subject': entry.subject.name,
                'teacher': f"{entry.teacher.user.first_name} {entry.teacher.user.last_name}",
                'room': entry.room_number,
                'notes': entry.notes,
                'subject_id': str(entry.subject.id),
                'teacher_id': str(entry.teacher.id),
            }
        
        return Response({
            'class_level': {
                'id': str(class_level.id),
                'name': class_level.name,
            },
            'academic_year': academic_year.name,
            'sections': list(sections_data.values())
        })

    # ------------------------------------------------------------------
    # Teacher Timetable
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='teacher/(?P<teacher_id>[^/.]+)')
    def teacher_timetable(self, request, teacher_id):
        """
        GET /api/v1/timetable/entries/teacher/{teacher_id}/
        Returns the timetable for a specific teacher.
        """
        try:
            teacher = TeacherProfile.objects.get(id=teacher_id, school=request.user.school)
        except TeacherProfile.DoesNotExist:
            return Response(
                {'detail': 'Teacher not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        academic_year_id = request.query_params.get('academic_year')
        try:
            if academic_year_id:
                academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
            else:
                academic_year = AcademicYear.objects.filter(
                    school=request.user.school,
                    is_active=True
                ).first()
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not academic_year:
            return Response(
                {'detail': 'Academic year not specified.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        entries = get_teacher_timetable(teacher, academic_year)
        timetable = organize_timetable_by_day(entries)
        
        # Format the timetable
        formatted_timetable = {}
        for day, periods in timetable.items():
            formatted_timetable[day] = {}
            for period, entry in periods.items():
                if entry:
                    formatted_timetable[day][period] = {
                        'id': str(entry.id),
                        'class_level': entry.class_level.name,
                        'section': entry.section.name,
                        'subject': entry.subject.name,
                        'room': entry.room_number,
                        'notes': entry.notes,
                        'class_level_id': str(entry.class_level.id),
                        'section_id': str(entry.section.id),
                        'subject_id': str(entry.subject.id),
                        'time_slot': {
                            'start_time': entry.time_slot.start_time.strftime('%H:%M'),
                            'end_time': entry.time_slot.end_time.strftime('%H:%M'),
                        }
                    }
        
        return Response({
            'teacher': {
                'id': str(teacher.id),
                'name': f"{teacher.user.first_name} {teacher.user.last_name}",
                'employee_id': teacher.employee_id,
            },
            'academic_year': academic_year.name,
            'timetable': formatted_timetable
        })

    # ------------------------------------------------------------------
    # Check conflicts
    # ------------------------------------------------------------------

    @action(detail=False, methods=['get'], url_path='conflicts')
    def check_conflicts(self, request):
        """
        GET /api/v1/timetable/entries/conflicts/
        Check for conflicts in the timetable.
        """
        academic_year_id = request.query_params.get('academic_year')
        if not academic_year_id:
            return Response(
                {'detail': 'academic_year is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        entries = TimetableEntry.objects.filter(
            school=request.user.school,
            academic_year=academic_year,
            is_active=True
        )
        
        conflicts = check_conflicts(entries)
        
        return Response({
            'academic_year': academic_year.name,
            'total_entries': entries.count(),
            'conflicts_found': len(conflicts),
            'conflicts': conflicts
        })


# ---------------------------------------------------------------------------
# TimetableTemplate ViewSet
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(summary="List timetable templates"),
    create=extend_schema(summary="Create a new timetable template"),
    retrieve=extend_schema(summary="Get template details"),
    update=extend_schema(summary="Update a template"),
    partial_update=extend_schema(summary="Partially update a template"),
    destroy=extend_schema(summary="Delete a template"),
)
class TimetableTemplateViewSet(TenantAwareModelViewSet):
    """
    Manage timetable templates.
    """
    queryset = TimetableTemplate.objects.all()
    serializer_class = TimetableTemplateSerializer
    permission_classes = [IsAuthenticated, IsSchoolAdminOrStaff]
    
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'description']
    
    def perform_create(self, serializer):
        serializer.save(
            school=self.request.user.school,
            created_by=self.request.user
        )
    
    @action(detail=True, methods=['post'], url_path='apply')
    def apply_template(self, request, pk=None):
        """
        POST /api/v1/timetable/templates/{id}/apply/
        Apply a template to create timetable entries.
        
        Body: { "academic_year_id": "uuid", "class_level_id": "uuid", "section_id": "uuid" }
        """
        template = self.get_object()
        
        academic_year_id = request.data.get('academic_year_id')
        class_level_id = request.data.get('class_level_id')
        section_id = request.data.get('section_id')
        
        if not academic_year_id:
            return Response(
                {'detail': 'academic_year_id is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            academic_year = AcademicYear.objects.get(id=academic_year_id, school=request.user.school)
        except AcademicYear.DoesNotExist:
            return Response(
                {'detail': 'Academic year not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get the template data
        template_data = template.data
        
        # Filter entries by class_level and section if provided
        entries_to_create = []
        for entry_data in template_data.get('entries', []):
            if class_level_id and entry_data.get('class_level_id') != class_level_id:
                continue
            if section_id and entry_data.get('section_id') != section_id:
                continue
            
            # Get the actual objects
            try:
                class_level = ClassLevel.objects.get(id=entry_data['class_level_id'], school=request.user.school)
                section = Section.objects.get(id=entry_data['section_id'], school=request.user.school)
                subject = Subject.objects.get(id=entry_data['subject_id'], school=request.user.school)
                teacher = TeacherProfile.objects.get(id=entry_data['teacher_id'], school=request.user.school)
                time_slot = TimeSlot.objects.get(id=entry_data['time_slot_id'], school=request.user.school)
            except (ClassLevel.DoesNotExist, Section.DoesNotExist, Subject.DoesNotExist,
                    TeacherProfile.DoesNotExist, TimeSlot.DoesNotExist) as e:
                return Response({
                    'detail': f'Invalid reference in template: {str(e)}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            entries_to_create.append(
                TimetableEntry(
                    school=request.user.school,
                    created_by=request.user,
                    academic_year=academic_year,
                    class_level=class_level,
                    section=section,
                    subject=subject,
                    teacher=teacher,
                    time_slot=time_slot,
                    room_number=entry_data.get('room_number', ''),
                    notes=entry_data.get('notes', ''),
                )
            )
        
        if not entries_to_create:
            return Response({
                'detail': 'No matching entries to create.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                created = TimetableEntry.objects.bulk_create(entries_to_create)
                return Response({
                    'detail': f'Successfully created {len(created)} timetable entries from template.',
                    'entries_created': len(created)
                }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({
                'detail': f'Failed to create entries: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)