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

# AI Content
router.register(r'saved-ai-content', SavedAIContentViewSet, basename='saved-ai-content')

urlpatterns = [
    path('', include(router.urls)),
]