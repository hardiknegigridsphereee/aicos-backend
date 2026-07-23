# finance/serializers.py
from rest_framework import serializers
from finance.models import FeeStructure, StudentFee, FeeTransaction

class FeeStructureSerializer(serializers.ModelSerializer):
    class_level_name = serializers.CharField(source='class_level.name', read_only=True)
    academic_year_name = serializers.CharField(source='academic_year.name', read_only=True)
    
    class Meta:
        model = FeeStructure
        fields = '__all__'
        read_only_fields = ['school', 'id', 'total_fee']


class StudentFeeSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    class_level_name = serializers.CharField(source='fee_structure.class_level.name', read_only=True)
    academic_year_name = serializers.CharField(source='fee_structure.academic_year.name', read_only=True)
    
    class Meta:
        model = StudentFee
        fields = '__all__'
        read_only_fields = ['school', 'id', 'total_fee', 'balance_due']


class StudentFeeDetailSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    student_email = serializers.EmailField(source='student.user.email', read_only=True)
    enrollment_number = serializers.CharField(source='student.enrollment_number', read_only=True)
    class_level_name = serializers.CharField(source='fee_structure.class_level.name', read_only=True)
    academic_year_name = serializers.CharField(source='fee_structure.academic_year.name', read_only=True)
    transactions = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentFee
        fields = [
            'id', 'student', 'student_name', 'student_email', 'enrollment_number',
            'fee_structure', 'class_level_name', 'academic_year_name',
            'tuition_fee', 'transport_fee', 'library_fee', 'lab_fee',
            'sports_fee', 'miscellaneous', 'total_fee',
            'amount_paid', 'balance_due', 'status', 'due_date',
            'transactions', 'created_at', 'updated_at'
        ]
    
    def get_transactions(self, obj):
        from finance.serializers import FeeTransactionSerializer
        transactions = obj.transactions.all().order_by('-payment_date')[:10]
        return FeeTransactionSerializer(transactions, many=True).data


class FeeTransactionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.first_name', read_only=True)
    created_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = FeeTransaction
        fields = '__all__'
        read_only_fields = ['school', 'id', 'transaction_id']
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
        return None
    
    def validate(self, attrs):
        import uuid
        attrs['transaction_id'] = f"FEE-{uuid.uuid4().hex[:12].upper()}"
        return attrs
