from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    # Core Academic
    AcademicYearViewSet,
    ClassLevelViewSet,
    SectionViewSet,
    SubjectViewSet,
    
    # Enrollments & Assignments
    StudentEnrollmentViewSet,
    TeacherAssignmentViewSet,
    
    # AI Content
    SavedAIContentViewSet,
    
    # ❌ REMOVE THESE - They don't exist in academics/views.py
    # AttendanceViewSet,
    # ExamViewSet,
    # StudentGradeViewSet,
    # AssignmentViewSet,
    # StudentSubmissionViewSet,
)

router = DefaultRouter()

# Core Academic
router.register(r'academic-years', AcademicYearViewSet, basename='academic-year')
router.register(r'class-levels', ClassLevelViewSet, basename='class-level')
router.register(r'sections', SectionViewSet, basename='section')
router.register(r'subjects', SubjectViewSet, basename='subject')

# Enrollments & Assignments
router.register(r'enrollments', StudentEnrollmentViewSet, basename='enrollment')
router.register(r'teacher-assignments', TeacherAssignmentViewSet, basename='teacher-assignment')

# ❌ REMOVE THESE - They're already registered in operations/urls.py
# router.register(r'attendance', AttendanceViewSet, basename='attendance')
# router.register(r'exams', ExamViewSet, basename='exam')
# router.register(r'grades', StudentGradeViewSet, basename='grade')
# router.register(r'assignments', AssignmentViewSet, basename='assignment')
# router.register(r'submissions', StudentSubmissionViewSet, basename='submission')

# AI Content
router.register(r'saved-ai-content', SavedAIContentViewSet, basename='saved-ai-content')

urlpatterns = [
    path('', include(router.urls)),
]
