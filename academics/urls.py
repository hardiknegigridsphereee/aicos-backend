from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    StudentEnrollmentViewSet, 
    TeacherAssignmentViewSet,
    AcademicYearViewSet,
    ClassLevelViewSet,
    SectionViewSet,
    SubjectViewSet,
    SavedAIContentViewSet
)

router = DefaultRouter()

# Register the new Core Academic routing
router.register(r'academic-years', AcademicYearViewSet, basename='academic-year')
router.register(r'class-levels', ClassLevelViewSet, basename='class-level')
router.register(r'sections', SectionViewSet, basename='section')
router.register(r'subjects', SubjectViewSet, basename='subject')

# Register existing routing
router.register(r'enrollments', StudentEnrollmentViewSet, basename='enrollment')
router.register(r'teacher-assignments', TeacherAssignmentViewSet, basename='teacher-assignment')
router.register(r'saved-ai-content', SavedAIContentViewSet, basename='saved-ai-content')

urlpatterns = [
    path('', include(router.urls)),
]