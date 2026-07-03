# profiles/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StudentProfileViewSet, TeacherProfileViewSet, 
    ParentProfileViewSet, ParentStudentMappingViewSet,
    UserContextView,
    # Location views
    StudentDeviceDetailView,
    StudentDeviceUpdateView,
    StudentUpdateLocationView,
    StudentLocationHistoryView,
    StudentLocationAdminView,
    ParentChildLocationView,
    ParentChildrenLocationsView,
)
from .student_dashboard import StudentDashboardAPIView
from .parent_dashboard import (
    ParentDashboardAPIView,
    ParentChildDetailAPIView,
    ParentChildAttendanceAPIView,
    ParentChildGradeReportAPIView,
    ParentSwitchChildAPIView,
    ParentActiveChildAPIView
)
from .parent_additions import (
    ParentChildAssignmentsAPIView,
    ParentChildSubmissionsAPIView
)
from .teacher_dashboard import (
    TeacherDashboardAPIView,
)

router = DefaultRouter()
router.register(r'students', StudentProfileViewSet, basename='student')
router.register(r'teachers', TeacherProfileViewSet, basename='teacher')
router.register(r'parents', ParentProfileViewSet, basename='parent')
router.register(r'parent-student-mappings', ParentStudentMappingViewSet, basename='parent-student-mapping')

urlpatterns = [
    # Task 2.4: Context Switching Endpoint
    path('me/', UserContextView.as_view(), name='user-context'),
    
    # Student Dashboard
    path('students/dashboard/', StudentDashboardAPIView.as_view(), name='student-dashboard'),
    
    # ✅ NEW: Student Subjects Endpoint
    # This uses the ViewSet's action, so it's automatically routed via the router
    # The URL will be: /api/v1/profiles/students/me/subjects/
    # No additional path needed here since it's registered via the router's @action decorator
    
    # ── LOCATION ROUTES ──────────────────────────────────────────────────────
    # Student device & location routes
    path('students/me/device/', StudentDeviceDetailView.as_view(), name='student-device'),
    path('students/me/device/update/', StudentDeviceUpdateView.as_view(), name='student-device-update'),
    path('students/me/location/update/', StudentUpdateLocationView.as_view(), name='student-location-update'),
    path('students/me/location/history/', StudentLocationHistoryView.as_view(), name='student-location-history'),
    
    # Admin/Staff location routes
    path('locations/students/<uuid:student_id>/', StudentLocationAdminView.as_view(), name='admin-student-location'),
    
    # Parent location routes
    path('parents/me/children/locations/', ParentChildrenLocationsView.as_view(), name='parent-children-locations'),
    path('parents/me/children/<uuid:child_id>/location/', ParentChildLocationView.as_view(), name='parent-child-location'),
    
    # Parent Dashboard & Child Management
    path('parents/dashboard/', ParentDashboardAPIView.as_view(), name='parent-dashboard'),
    path('parents/me/children/<uuid:child_id>/', ParentChildDetailAPIView.as_view(), name='parent-child-detail'),
    path('parents/me/children/<uuid:child_id>/attendance/', ParentChildAttendanceAPIView.as_view(), name='parent-child-attendance'),
    path('parents/me/children/<uuid:child_id>/grades/', ParentChildGradeReportAPIView.as_view(), name='parent-child-grades'),
    path('parents/me/children/<uuid:child_id>/assignments/', ParentChildAssignmentsAPIView.as_view(), name='parent-child-assignments'),
    path('parents/me/children/<uuid:child_id>/submissions/', ParentChildSubmissionsAPIView.as_view(), name='parent-child-submissions'),
    path('parents/me/children/switch/', ParentSwitchChildAPIView.as_view(), name='parent-switch-child'),
    path('parents/me/children/active/', ParentActiveChildAPIView.as_view(), name='parent-active-child'),
    
    # Teacher Dashboard
    path('teachers/dashboard/', TeacherDashboardAPIView.as_view(), name='teacher-dashboard'),
    
    # Task 2.3: Profile ViewSets Endpoints
    path('', include(router.urls)),
]