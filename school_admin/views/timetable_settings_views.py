# school_admin/views/timetable_settings_views.py
from rest_framework import status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView
from drf_spectacular.utils import extend_schema, extend_schema_view

from school_admin.models import TimetableSettings, TimetableConfigHistory
from school_admin.serializers.timetable_settings_serializers import (
    TimetableSettingsSerializer,
    TimetableSettingsCreateSerializer,
    TimetableSettingsUpdateSerializer,
    TimetableSettingsHistorySerializer,
    TimetableSettingsCheckSerializer,
)
from school_admin.views.school_admin_views import IsSchoolAdminOrStaff


class TimetableSettingsCheckAPIView(APIView):
    """
    GET /api/v1/school-admin/timetable-settings/check/
    Check if timetable settings exist.
    Used for onboarding flow.
    """
    permission_classes = [IsAuthenticated, IsSchoolAdminOrStaff]

    def get(self, request):
        settings_exists = TimetableSettings.objects.filter(school=request.user.school).exists()
        
        return Response({
            'exists': settings_exists,
            'has_settings': settings_exists,
            'message': 'Timetable settings already configured. Please update or proceed to subject assignment.' if settings_exists else 'No timetable settings found. Please complete the onboarding.'
        })


class TimetableSettingsOnboardAPIView(APIView):
    """
    POST /api/v1/school-admin/timetable-settings/onboard/
    Create timetable settings for the first time (onboarding).
    ALL fields are required - no defaults.
    """
    permission_classes = [IsAuthenticated, IsSchoolAdminOrStaff]

    def post(self, request):
        # Check if settings already exist
        if TimetableSettings.objects.filter(school=request.user.school).exists():
            return Response(
                {'detail': 'Timetable settings already exist. Use the update endpoint to modify them.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = TimetableSettingsCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        # Create new settings
        settings = TimetableSettings.objects.create(
            school=request.user.school,
            updated_by=request.user,
            **serializer.validated_data
        )
        
        # Convert time objects to strings for JSON serialization
        data_for_history = {}
        for key, value in serializer.validated_data.items():
            if hasattr(value, 'strftime'):  # Check if it's a time/datetime object
                data_for_history[key] = value.strftime('%H:%M:%S')
            else:
                data_for_history[key] = value
        
        # Create history entry
        TimetableConfigHistory.objects.create(
            school=request.user.school,
            timetable_settings=settings,
            changed_by=request.user,
            changes={'action': 'onboard', 'data': data_for_history}
        )
        
        response_serializer = TimetableSettingsSerializer(settings)
        return Response(
            {
                'detail': 'Timetable settings created successfully! You can now assign subjects to periods.',
                'data': response_serializer.data
            },
            status=status.HTTP_201_CREATED
        )


class TimetableSettingsAPIView(APIView):
    """
    GET /api/v1/school-admin/timetable-settings/
    Retrieve the current timetable settings for the school.
    
    PUT /api/v1/school-admin/timetable-settings/
    Update timetable settings (all fields required).
    
    PATCH /api/v1/school-admin/timetable-settings/
    Partially update timetable settings.
    """
    permission_classes = [IsAuthenticated, IsSchoolAdminOrStaff]

    def get(self, request):
        try:
            settings = TimetableSettings.objects.get(school=request.user.school)
        except TimetableSettings.DoesNotExist:
            return Response(
                {'detail': 'Timetable settings not configured. Please complete onboarding.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TimetableSettingsSerializer(settings)
        return Response(serializer.data)

    def put(self, request):
        try:
            settings = TimetableSettings.objects.get(school=request.user.school)
        except TimetableSettings.DoesNotExist:
            return Response(
                {'detail': 'Timetable settings not configured. Please complete onboarding first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TimetableSettingsUpdateSerializer(
            settings,
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        # Track changes before saving
        old_data = {}
        for field in serializer.validated_data.keys():
            old_value = getattr(settings, field, None)
            if old_value is not None:
                # Convert time objects to strings
                if hasattr(old_value, 'strftime'):
                    old_data[field] = old_value.strftime('%H:%M:%S')
                else:
                    old_data[field] = old_value
        
        # Save the settings
        updated_settings = serializer.save(updated_by=request.user)
        
        # Create history entry
        if old_data:
            changes = {}
            for field, old_value in old_data.items():
                new_value = getattr(updated_settings, field, None)
                # Convert time objects to strings
                if hasattr(new_value, 'strftime'):
                    new_value_str = new_value.strftime('%H:%M:%S')
                else:
                    new_value_str = str(new_value) if new_value is not None else None
                
                if old_value != new_value_str:
                    changes[field] = {
                        'old': str(old_value) if old_value is not None else None,
                        'new': str(new_value_str) if new_value_str is not None else None
                    }
            
            if changes:
                TimetableConfigHistory.objects.create(
                    school=request.user.school,
                    timetable_settings=updated_settings,
                    changed_by=request.user,
                    changes=changes
                )
        
        response_serializer = TimetableSettingsSerializer(updated_settings)
        return Response(
            {
                'detail': 'Timetable settings updated successfully.',
                'data': response_serializer.data
            },
            status=status.HTTP_200_OK
        )

    def patch(self, request):
        try:
            settings = TimetableSettings.objects.get(school=request.user.school)
        except TimetableSettings.DoesNotExist:
            return Response(
                {'detail': 'Timetable settings not configured. Please complete onboarding first.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = TimetableSettingsUpdateSerializer(
            settings,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        updated_settings = serializer.save(updated_by=request.user)
        
        # Create history entry for partial updates
        changes = {}
        for field, new_value in serializer.validated_data.items():
            old_value = getattr(settings, field, None)
            
            # Convert time objects to strings for comparison
            if hasattr(old_value, 'strftime'):
                old_value_str = old_value.strftime('%H:%M:%S')
            else:
                old_value_str = str(old_value) if old_value is not None else None
            
            if hasattr(new_value, 'strftime'):
                new_value_str = new_value.strftime('%H:%M:%S')
            else:
                new_value_str = str(new_value) if new_value is not None else None
            
            if old_value_str != new_value_str:
                changes[field] = {
                    'old': old_value_str,
                    'new': new_value_str
                }
        
        if changes:
            TimetableConfigHistory.objects.create(
                school=request.user.school,
                timetable_settings=updated_settings,
                changed_by=request.user,
                changes=changes
            )
        
        response_serializer = TimetableSettingsSerializer(updated_settings)
        return Response(
            {
                'detail': 'Timetable settings updated successfully.',
                'data': response_serializer.data
            },
            status=status.HTTP_200_OK
        )


class TimetableSettingsHistoryAPIView(ListAPIView):
    """
    GET /api/v1/school-admin/timetable-settings/history/
    Retrieve change history for timetable settings.
    """
    permission_classes = [IsAuthenticated, IsSchoolAdminOrStaff]
    serializer_class = TimetableSettingsHistorySerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['changed_at']
    ordering = ['-changed_at']

    def get_queryset(self):
        return TimetableConfigHistory.objects.filter(
            school=self.request.user.school
        ).select_related('changed_by')