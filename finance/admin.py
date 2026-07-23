# finance/admin.py
from django.contrib import admin
from finance.models import FeeStructure, StudentFee, FeeTransaction

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ('class_level', 'academic_year', 'total_fee', 'due_date', 'is_active', 'school')
    list_filter = ('school', 'academic_year', 'class_level', 'is_active')
    search_fields = ('class_level__name', 'academic_year__name')

@admin.register(StudentFee)
class StudentFeeAdmin(admin.ModelAdmin):
    list_display = ('student', 'fee_structure', 'total_fee', 'amount_paid', 'balance_due', 'status', 'due_date')
    list_filter = ('school', 'status', 'fee_structure__academic_year', 'fee_structure__class_level')
    search_fields = ('student__user__first_name', 'student__user__email', 'student__enrollment_number')

@admin.register(FeeTransaction)
class FeeTransactionAdmin(admin.ModelAdmin):
    list_display = ('student', 'amount', 'payment_method', 'transaction_id', 'status', 'payment_date')
    list_filter = ('school', 'payment_method', 'status')
    search_fields = ('student__user__first_name', 'student__user__email', 'transaction_id')
    date_hierarchy = 'payment_date'
