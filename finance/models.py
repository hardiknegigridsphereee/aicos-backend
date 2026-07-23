# finance/models.py
import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from tenants.models import TenantAwareModel

class FeeStructure(TenantAwareModel):
    """
    Defines fee structure for each class and academic year
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    academic_year = models.ForeignKey('academics.AcademicYear', on_delete=models.CASCADE, related_name='fee_structures')
    class_level = models.ForeignKey('academics.ClassLevel', on_delete=models.CASCADE, related_name='fee_structures')
    
    # Fee components
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    library_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lab_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sports_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    miscellaneous = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    total_fee = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    due_date = models.DateField()
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['academic_year__start_date', 'class_level__numeric_order']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'academic_year', 'class_level'],
                name='unique_fee_structure_per_class_year'
            )
        ]
    
    def save(self, *args, **kwargs):
        self.total_fee = (
            self.tuition_fee + 
            self.transport_fee + 
            self.library_fee + 
            self.lab_fee + 
            self.sports_fee + 
            self.miscellaneous
        )
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.class_level.name} - {self.academic_year.name} (₹{self.total_fee})"


class StudentFee(TenantAwareModel):
    """
    Individual student fee record
    """
    class PaymentStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        PARTIAL = 'Partial', 'Partially Paid'
        PAID = 'Paid', 'Fully Paid'
        OVERDUE = 'Overdue', 'Overdue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='fees')
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.CASCADE, related_name='student_fees')
    
    enrollment = models.ForeignKey('academics.StudentEnrollment', on_delete=models.CASCADE, related_name='fees', null=True, blank=True)
    
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    transport_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    library_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lab_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sports_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    miscellaneous = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_fee = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=10, decimal_places=2, editable=False, default=0)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    due_date = models.DateField()
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['student__user__last_name', 'student__user__first_name']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'student', 'fee_structure'],
                name='unique_student_fee_per_structure'
            )
        ]
    
    def save(self, *args, **kwargs):
        self.total_fee = (
            self.tuition_fee + 
            self.transport_fee + 
            self.library_fee + 
            self.lab_fee + 
            self.sports_fee + 
            self.miscellaneous
        )
        self.balance_due = self.total_fee - self.amount_paid
        
        if self.amount_paid >= self.total_fee:
            self.status = self.PaymentStatus.PAID
        elif self.amount_paid > 0:
            self.status = self.PaymentStatus.PARTIAL
        elif self.due_date and self.due_date < timezone.now().date():
            self.status = self.PaymentStatus.OVERDUE
        else:
            self.status = self.PaymentStatus.PENDING
        
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.student.user.first_name} - {self.fee_structure.class_level.name} (₹{self.total_fee})"


class FeeTransaction(TenantAwareModel):
    """
    Individual payment transactions
    """
    class PaymentMethod(models.TextChoices):
        CASH = 'Cash', 'Cash'
        CHEQUE = 'Cheque', 'Cheque'
        BANK_TRANSFER = 'Bank_Transfer', 'Bank Transfer'
        ONLINE = 'Online', 'Online Payment'
        CARD = 'Card', 'Credit/Debit Card'
        OTHER = 'Other', 'Other'

    class TransactionStatus(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        COMPLETED = 'Completed', 'Completed'
        FAILED = 'Failed', 'Failed'
        REFUNDED = 'Refunded', 'Refunded'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student_fee = models.ForeignKey(StudentFee, on_delete=models.CASCADE, related_name='transactions')
    student = models.ForeignKey('profiles.StudentProfile', on_delete=models.CASCADE, related_name='fee_transactions')
    
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    transaction_id = models.CharField(max_length=100, unique=True)
    reference_number = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=TransactionStatus.choices, default=TransactionStatus.COMPLETED)
    
    transaction_date = models.DateTimeField(auto_now_add=True)
    payment_date = models.DateField()
    created_by = models.ForeignKey('tenants.User', on_delete=models.SET_NULL, null=True, related_name='fee_transactions_created')
    
    class Meta:
        ordering = ['-payment_date', '-transaction_date']
        indexes = [
            models.Index(fields=['student', 'payment_date']),
            models.Index(fields=['transaction_id']),
        ]
    
    def __str__(self):
        return f"{self.student.user.first_name} - ₹{self.amount} ({self.payment_method})"
