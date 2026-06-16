from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from school_admin.models import SchoolSettings
from school_admin.serializers.settings_serializers import SchoolSettingsSerializer

class SchoolSettingsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        settings, created = SchoolSettings.objects.get_or_create(school=request.user.school)
        serializer = SchoolSettingsSerializer(settings)
        return Response(serializer.data)

    def put(self, request):
        settings, created = SchoolSettings.objects.get_or_create(school=request.user.school)
        serializer = SchoolSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)   # ✅ fixed: return saved data
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)