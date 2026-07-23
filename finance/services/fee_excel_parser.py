# finance/services/fee_excel_parser.py
import pandas as pd
import io
import re
from datetime import datetime
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError

class FeeExcelParser:
    """Parses fee management Excel files"""
    
    REQUIRED_FIELDS = [
        'student_email', 'enrollment_number', 'first_name', 'last_name',
        'class_name', 'section_name', 'academic_year',
        'tuition_fee', 'due_date'
    ]
    
    @staticmethod
    def parse_excel(file_buffer):
        """
        Parse Excel file and return list of dictionaries.
        Handles both file-like objects and bytes.
        """
        try:
            # If file_buffer is bytes, convert to BytesIO
            if isinstance(file_buffer, bytes):
                print(f"🔍 Converting bytes to BytesIO (size: {len(file_buffer)} bytes)")
                file_buffer = io.BytesIO(file_buffer)
            
            # Read the Excel file
            df = pd.read_excel(file_buffer, dtype=str)
            df = df.fillna('')
            
            # Clean column names
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
            
            data = df.to_dict('records')
            print(f"🔍 Parsed {len(data)} rows from Excel")
            return data
        except Exception as e:
            print(f"❌ Error parsing Excel: {str(e)}")
            raise ValueError(f"Failed to parse Excel file: {str(e)}")
    
    @staticmethod
    def validate_headers(data):
        """Validate that all required columns exist"""
        if not data:
            raise ValueError("Excel file is empty")
        
        headers = set(data[0].keys())
        missing = set(FeeExcelParser.REQUIRED_FIELDS) - headers
        
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        
        return True
    
    @staticmethod
    def validate_row(row):
        """Validate a single row"""
        errors = []
        row_num = row.get('_row_num', 0)
        
        # Check required fields
        for field in FeeExcelParser.REQUIRED_FIELDS:
            value = row.get(field, '').strip()
            if not value:
                errors.append(f"Row {row_num}: {field} is required")
        
        # Email validation
        email = row.get('student_email', '').strip()
        if email:
            try:
                EmailValidator()(email)
            except ValidationError:
                errors.append(f"Row {row_num}: Invalid student email format: {email}")
        
        # Numeric validations
        numeric_fields = ['tuition_fee', 'transport_fee', 'library_fee', 
                         'lab_fee', 'sports_fee', 'miscellaneous', 'amount_paid']
        for field in numeric_fields:
            value = row.get(field, '').strip()
            if value:
                try:
                    float(value)
                except ValueError:
                    errors.append(f"Row {row_num}: {field} must be a number: {value}")
        
        # Date validation
        due_date = row.get('due_date', '').strip()
        if due_date:
            try:
                datetime.strptime(due_date, '%Y-%m-%d')
            except ValueError:
                errors.append(f"Row {row_num}: Invalid date format. Use YYYY-MM-DD: {due_date}")
        
        return errors
