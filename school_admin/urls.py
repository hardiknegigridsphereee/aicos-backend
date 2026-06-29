from django.urls import path
from .views.dashboard_views import (
    DashboardStatsAPIView,
    EnrollmentTrendAPIView,
    NotificationListAPIView,
    ActivityLogListAPIView,
)
from school_admin.views.staff_views import OnboardStudentAPIView, OnboardTeacherAPIView,OnboardParentAPIView
from .views.settings_views import SchoolSettingsAPIView
from .views.school_admin_views import (
    SchoolAdminStudentListView,
    SchoolAdminTeacherListView,
    SchoolAdminTeacherAssignmentListView,
    SchoolAdminParentStudentMappingListView,
    SchoolAdminParentListView,
)

urlpatterns = [
    # ── Dashboard ──────────────────────────────────────────────────────────
    path('dashboard/stats/', DashboardStatsAPIView.as_view(), name='admin-dashboard-stats'),
    path('dashboard/trends/', EnrollmentTrendAPIView.as_view(), name='admin-dashboard-trends'),

    # ── Notifications & Logs ───────────────────────────────────────────────
    path('notifications/', NotificationListAPIView.as_view(), name='admin-notifications-list'),
    path('logs/', ActivityLogListAPIView.as_view(), name='admin-activity-logs'),

    # ── Onboarding ─────────────────────────────────────────────────────────
    path('staff/students/register/', OnboardStudentAPIView.as_view(), name='admin-register-student'),
    path('staff/teachers/register/', OnboardTeacherAPIView.as_view(), name='admin-register-teacher'),

    # ── Settings ───────────────────────────────────────────────────────────
    path('settings/', SchoolSettingsAPIView.as_view(), name='school-settings'),

    # ── People & Assignments ───────────────────────────────────────────────
    path('students/', SchoolAdminStudentListView.as_view(), name='admin-student-list'),
    path('teachers/', SchoolAdminTeacherListView.as_view(), name='admin-teacher-list'),
    path('parents/', SchoolAdminParentListView.as_view(), name='admin-parent-list'),
    path('teacher-assignments/', SchoolAdminTeacherAssignmentListView.as_view(), name='admin-teacher-assignment-list'),
    path('parent-student-mappings/', SchoolAdminParentStudentMappingListView.as_view(), name='admin-parent-student-mapping-list'),
    path('staff/parents/register/', OnboardParentAPIView.as_view(), name='admin-register-parent'),
]