from django.contrib import admin

from .models import LeaveRequest


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'school', 'applicant_role', 'applicant_name', 'leave_type',
        'start_date', 'end_date', 'status', 'applied_at', 'reviewed_by',
    )
    list_filter = ('school', 'applicant_role', 'status', 'leave_type')
    search_fields = (
        'student__user__first_name', 'student__user__last_name',
        'teacher__user__first_name', 'teacher__user__last_name',
        'reason',
    )
    readonly_fields = ('id', 'applied_at')
