# profiles/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StudentProfileViewSet, TeacherProfileViewSet, 
    ParentProfileViewSet, ParentStudentMappingViewSet,
    UserContextView
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