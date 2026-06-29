from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AttendanceViewSet, ExamViewSet, StudentGradeViewSet, 
    AssignmentViewSet, StudentSubmissionViewSet
)

router = DefaultRouter()
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'grades', StudentGradeViewSet, basename='grade')
router.register(r'assignments', AssignmentViewSet, basename='assignment')
router.register(r'submissions', StudentSubmissionViewSet, basename='submission')

# Note: The @action decorators in views.py will automatically add these routes:
# - attendance/me/today/
# - attendance/me/section/{id}/
# - attendance/me/summary/
# - grades/me/section/{id}/exam/{id}/
# - assignments/me/
# - submissions/me/pending/
# - submissions/me/assignment/{id}/
# - submissions/me/ (already exists)

urlpatterns = [
    path('', include(router.urls)),
]