# school_admin/admin.py
from django.contrib import admin
from .models import Circular


@admin.register(Circular)
class CircularAdmin(admin.ModelAdmin):
    list_display   = ('title', 'target_audience', 'is_published', 'school', 'created_by', 'created_at')
    list_filter    = ('school', 'target_audience', 'is_published')
    search_fields  = ('title', 'content')
    filter_horizontal = ('target_class_levels',)
    readonly_fields   = ('created_at', 'updated_at', 'created_by')

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
