from django.urls import path
from .views.dashboard_views import (
    DashboardStatsAPIView,
    EnrollmentTrendAPIView,
    NotificationListAPIView,
    ActivityLogListAPIView,
    # <-- Import the new view
)
from school_admin.views.staff_views import OnboardStudentAPIView, OnboardTeacherAPIView
from .views.settings_views import SchoolSettingsAPIView
urlpatterns = [
    path('dashboard/stats/', DashboardStatsAPIView.as_view(), name='admin-dashboard-stats'),
    path('dashboard/trends/', EnrollmentTrendAPIView.as_view(), name='admin-dashboard-trends'),
    path('notifications/', NotificationListAPIView.as_view(), name='admin-notifications-list'),
    path('logs/', ActivityLogListAPIView.as_view(), name='admin-activity-logs'),
    path('staff/students/register/', OnboardStudentAPIView.as_view(), name='admin-register-student'),
    path('staff/teachers/register/', OnboardTeacherAPIView.as_view(), name='admin-register-teacher'),
    path('settings/', SchoolSettingsAPIView.as_view(), name='school-settings'),
]