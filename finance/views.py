# finance/views.py
from rest_framework import viewsets, status, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view

from tenants.views import TenantAwareModelViewSet
from accounts.permissions import IsTeacherOrStaff, IsStudent, IsParent
from profiles.models import StudentProfile, ParentProfile, ParentStudentMapping
from academics.models import StudentEnrollment

from finance.models import FeeStructure, StudentFee, FeeTransaction
from finance.serializers import (
    FeeStructureSerializer, StudentFeeSerializer, FeeTransactionSerializer,
    StudentFeeDetailSerializer
)
from finance.services import FeeBulkUploadService


@extend_schema_view(
    list=extend_schema(summary="List fee structures"),
    create=extend_schema(summary="Create fee structure"),
    retrieve=extend_schema(summary="Get fee structure details"),
    update=extend_schema(summary="Update fee structure"),
    partial_update=extend_schema(summary="Partially update fee structure"),
    destroy=extend_schema(summary="Delete fee structure"),
)
class FeeStructureViewSet(TenantAwareModelViewSet):
    queryset = FeeStructure.objects.select_related('academic_year', 'class_level').all()
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['academic_year', 'class_level', 'is_active']
    search_fields = ['class_level__name', 'academic_year__name']


@extend_schema_view(
    list=extend_schema(summary="List student fees"),
    retrieve=extend_schema(summary="Get student fee details"),
)
class StudentFeeViewSet(TenantAwareModelViewSet):
    queryset = StudentFee.objects.select_related(
        'student__user', 'fee_structure__class_level', 'fee_structure__academic_year'
    ).all()
    serializer_class = StudentFeeSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'my_fees', 'my_fee_summary']:
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsTeacherOrStaff()]

    def get_serializer_class(self):
        if self.action in ['retrieve', 'my_fees']:
            return StudentFeeDetailSerializer
        return StudentFeeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        
        if hasattr(user, 'studentprofile'):
            student = user.studentprofile
            return qs.filter(student=student)
        
        if hasattr(user, 'parentprofile'):
            parent = user.parentprofile
            student_ids = ParentStudentMapping.objects.filter(
                parent=parent,
                school=user.school
            ).values_list('student_id', flat=True)
            return qs.filter(student_id__in=student_ids)
        
        return qs

    @action(detail=False, methods=['get'], url_path='me')
    def my_fees(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        fees = StudentFee.objects.filter(
            student=student,
            school=request.user.school,
            is_active=True
        ).select_related('fee_structure__class_level', 'fee_structure__academic_year')
        
        serializer = StudentFeeDetailSerializer(fees, many=True)
        return Response({
            "count": fees.count(),
            "results": serializer.data
        })

    @action(detail=False, methods=['get'], url_path='me/summary')
    def my_fee_summary(self, request):
        try:
            student = StudentProfile.objects.get(user=request.user, school=request.user.school)
        except StudentProfile.DoesNotExist:
            return Response(
                {"detail": "Student profile not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        
        fees = StudentFee.objects.filter(
            student=student,
            school=request.user.school
        )
        
        total_fee = sum(f.total_fee for f in fees)
        total_paid = sum(f.amount_paid for f in fees)
        balance = total_fee - total_paid
        
        return Response({
            "student_name": f"{student.user.first_name} {student.user.last_name}",
            "enrollment_number": student.enrollment_number,
            "total_fee": float(total_fee),
            "total_paid": float(total_paid),
            "balance_due": float(balance),
            "fee_count": fees.count(),
            "pending_fees": fees.filter(status='Pending').count(),
            "overdue_fees": fees.filter(status='Overdue').count(),
            "paid_fees": fees.filter(status='Paid').count()
        })

    @action(detail=False, methods=['post'], url_path='bulk-upload', parser_classes=[MultiPartParser, FormParser])
    def bulk_upload(self, request):
        """
        POST /api/v1/finance/student-fees/bulk-upload/
        Upload Excel file with fee data
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file = request.FILES['file']
        
        if not file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'File must be an Excel file (.xlsx or .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            service = FeeBulkUploadService(
                school=request.user.school,
                user=request.user
            )
            
            options = {
                'update_existing': request.data.get('update_existing', 'true').lower() == 'true',
                'batch_size': int(request.data.get('batch_size', 50)),
            }
            
            results = service.process(
                file_buffer=file.read(),
                file_name=file.name,
                options=options
            )
            
            return Response({
                'summary': {
                    'total': results['total'],
                    'successful': results['successful'],
                    'failed': results['failed'],
                    'created': len(results['created']),
                    'updated': len(results['updated']),
                    'skipped': len(results['skipped']),
                },
                'errors': results['errors'][:20]
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FeeTransactionViewSet(TenantAwareModelViewSet):
    queryset = FeeTransaction.objects.select_related('student__user', 'student_fee').all()
    serializer_class = FeeTransactionSerializer
    permission_classes = [IsAuthenticated, IsTeacherOrStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'payment_method', 'status']
    search_fields = ['transaction_id', 'reference_number']
    ordering_fields = ['payment_date', 'amount']
    ordering = ['-payment_date']
