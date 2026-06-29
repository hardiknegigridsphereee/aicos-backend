# timetable/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TimeSlotViewSet,
    TimetableEntryViewSet,
    TimetableTemplateViewSet,
)

router = DefaultRouter()
router.register(r'time-slots', TimeSlotViewSet, basename='time-slot')
router.register(r'entries', TimetableEntryViewSet, basename='timetable-entry')
router.register(r'templates', TimetableTemplateViewSet, basename='timetable-template')

urlpatterns = [
    path('', include(router.urls)),
]