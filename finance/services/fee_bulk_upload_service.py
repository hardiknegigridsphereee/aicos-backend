# finance/services/fee_bulk_upload_service.py
from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime

from profiles.models import StudentProfile
from academics.models import ClassLevel, Section, AcademicYear, StudentEnrollment
from finance.models import FeeStructure, StudentFee
from finance.services.fee_excel_parser import FeeExcelParser

User = get_user_model()

class FeeBulkUploadService:
    """Service for bulk uploading fee data"""
    
    def __init__(self, school, user):
        self.school = school
        self.user = user
        self.results = {
            'total': 0,
            'successful': 0,
            'failed': 0,
            'errors': [],
            'created': [],
            'updated': [],
            'skipped': []
        }
    
    def process(self, file_buffer, file_name, options=None):
        """Main processing method"""
        options = options or {}
        
        try:
            print(f"📊 Processing fee upload: {file_name}")
            print(f"�� File buffer type: {type(file_buffer)}")
            
            # Parse Excel
            data = FeeExcelParser.parse_excel(file_buffer)
            FeeExcelParser.validate_headers(data)
            
            self.results['total'] = len(data)
            print(f"📊 Found {len(data)} rows to process")
            
            # Add row numbers
            for idx, row in enumerate(data):
                row['_row_num'] = idx + 2
            
            # Process in batches
            batch_size = options.get('batch_size', 50)
            self._process_batches(data, batch_size, options)
            
            print(f"✅ Processing complete: {self.results['successful']} successful, {self.results['failed']} failed")
            return self.results
            
        except Exception as e:
            print(f"❌ Failed to process fee upload: {str(e)}")
            raise ValueError(f"Failed to process fee upload: {str(e)}")
    
    def _process_batches(self, data, batch_size, options):
        """Process data in batches"""
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            self._process_batch(batch, options)
    
    def _process_batch(self, batch, options):
        """Process a single batch"""
        for row in batch:
            try:
                result = self._process_row(row, options)
                
                if result['status'] == 'created':
                    self.results['created'].append(result['data'])
                    self.results['successful'] += 1
                elif result['status'] == 'updated':
                    self.results['updated'].append(result['data'])
                    self.results['successful'] += 1
                elif result['status'] == 'skipped':
                    self.results['skipped'].append(result['data'])
                    self.results['successful'] += 1
                    
            except Exception as e:
                self.results['failed'] += 1
                self.results['errors'].append({
                    'row': row.get('_row_num', 0),
                    'data': {k: v for k, v in row.items() if not k.startswith('_')},
                    'error': str(e)
                })
    
    def _process_row(self, row, options):
        """Process a single row"""
        errors = FeeExcelParser.validate_row(row)
        if errors:
            raise ValidationError(f"Validation failed: {'; '.join(errors)}")
        
        student_email = row.get('student_email', '').strip()
        student = StudentProfile.objects.filter(
            user__email=student_email,
            school=self.school
        ).first()
        
        if not student:
            raise ValidationError(f"Student with email '{student_email}' not found")
        
        class_name = row.get('class_name', '').strip()
        class_level = ClassLevel.objects.filter(
            school=self.school,
            name__iexact=class_name
        ).first()
        
        if not class_level:
            raise ValidationError(f"Class '{class_name}' not found")
        
        section_name = row.get('section_name', '').strip()
        section = Section.objects.filter(
            school=self.school,
            class_level=class_level,
            name__iexact=section_name
        ).first()
        
        if not section:
            raise ValidationError(f"Section '{section_name}' not found")
        
        academic_year_name = row.get('academic_year', '').strip()
        academic_year = AcademicYear.objects.filter(
            school=self.school,
            name__iexact=academic_year_name
        ).first()
        
        if not academic_year:
            raise ValidationError(f"Academic year '{academic_year_name}' not found")
        
        enrollment = StudentEnrollment.objects.filter(
            school=self.school,
            student=student,
            academic_year=academic_year
        ).first()
        
        if not enrollment:
            enrollment = StudentEnrollment.objects.create(
                school=self.school,
                student=student,
                academic_year=academic_year,
                class_level=class_level,
                section=section,
                roll_number=row.get('roll_number', '')
            )
        
        fee_structure, _ = FeeStructure.objects.get_or_create(
            school=self.school,
            academic_year=academic_year,
            class_level=class_level,
            defaults={
                'tuition_fee': float(row.get('tuition_fee', 0)),
                'transport_fee': float(row.get('transport_fee', 0)),
                'library_fee': float(row.get('library_fee', 0)),
                'lab_fee': float(row.get('lab_fee', 0)),
                'sports_fee': float(row.get('sports_fee', 0)),
                'miscellaneous': float(row.get('miscellaneous', 0)),
                'due_date': datetime.strptime(row['due_date'], '%Y-%m-%d').date(),
            }
        )
        
        with transaction.atomic():
            student_fee, created = StudentFee.objects.get_or_create(
                school=self.school,
                student=student,
                fee_structure=fee_structure,
                defaults={
                    'enrollment': enrollment,
                    'tuition_fee': float(row.get('tuition_fee', 0)),
                    'transport_fee': float(row.get('transport_fee', 0)),
                    'library_fee': float(row.get('library_fee', 0)),
                    'lab_fee': float(row.get('lab_fee', 0)),
                    'sports_fee': float(row.get('sports_fee', 0)),
                    'miscellaneous': float(row.get('miscellaneous', 0)),
                    'due_date': datetime.strptime(row['due_date'], '%Y-%m-%d').date(),
                    'amount_paid': float(row.get('amount_paid', 0)),
                }
            )
            
            if not created and options.get('update_existing', False):
                student_fee.tuition_fee = float(row.get('tuition_fee', student_fee.tuition_fee))
                student_fee.transport_fee = float(row.get('transport_fee', student_fee.transport_fee))
                student_fee.library_fee = float(row.get('library_fee', student_fee.library_fee))
                student_fee.lab_fee = float(row.get('lab_fee', student_fee.lab_fee))
                student_fee.sports_fee = float(row.get('sports_fee', student_fee.sports_fee))
                student_fee.miscellaneous = float(row.get('miscellaneous', student_fee.miscellaneous))
                student_fee.due_date = datetime.strptime(row['due_date'], '%Y-%m-%d').date()
                if row.get('amount_paid'):
                    student_fee.amount_paid = float(row.get('amount_paid', 0))
                student_fee.save()
            
            return {
                'status': 'updated' if not created else 'created',
                'data': {
                    'id': str(student_fee.id),
                    'student_email': student_email,
                    'class': class_name,
                    'section': section_name,
                    'total_fee': float(student_fee.total_fee),
                    'amount_paid': float(student_fee.amount_paid),
                    'balance_due': float(student_fee.balance_due),
                    'status': student_fee.status
                }
            }
