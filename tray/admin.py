from django.contrib import admin
from .models import Tray, TrayRecord, InventoryRecord, AbnormalHandling, ReviewTask


@admin.register(Tray)
class TrayAdmin(admin.ModelAdmin):
    list_display = ['tray_code', 'capacity', 'area', 'applicable_sessions', 'responsible_person', 'status', 'created_at']
    list_filter = ['status', 'area', 'responsible_person']
    search_fields = ['tray_code', 'area', 'responsible_person', 'applicable_sessions']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(TrayRecord)
class TrayRecordAdmin(admin.ModelAdmin):
    list_display = ['tray', 'session', 'receiver', 'receive_time', 'return_time', 'is_returned', 'created_at']
    list_filter = ['is_returned', 'session', 'receiver']
    search_fields = ['tray__tray_code', 'session', 'receiver']
    readonly_fields = ['created_at']


@admin.register(InventoryRecord)
class InventoryRecordAdmin(admin.ModelAdmin):
    list_display = ['tray', 'actual_count', 'expected_count', 'diff_count', 'confirm_status', 'confirmer', 'confirm_time', 'inventory_time']
    list_filter = ['confirm_status', 'confirmer']
    search_fields = ['tray__tray_code', 'diff_description', 'conclusion']
    readonly_fields = ['created_at', 'inventory_time']


@admin.register(AbnormalHandling)
class AbnormalHandlingAdmin(admin.ModelAdmin):
    list_display = ['tray', 'source', 'handler', 'status', 'expected_completion_time', 'resolved_at', 'closed_at', 'created_at']
    list_filter = ['status', 'source', 'handler', 'tray__area']
    search_fields = ['tray__tray_code', 'handler', 'description', 'measures', 'result']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at', 'closed_at']


@admin.register(ReviewTask)
class ReviewTaskAdmin(admin.ModelAdmin):
    list_display = [
        'task_code', 'tray', 'source', 'status', 'reviewer',
        'priority', 'review_result', 'created_at', 'completed_time'
    ]
    list_filter = [
        'status', 'source', 'priority', 'review_result',
        'reviewer', 'tray__area'
    ]
    search_fields = [
        'task_code', 'tray__tray_code', 'reviewer', 'description',
        'review_opinion', 'creator'
    ]
    readonly_fields = [
        'created_at', 'updated_at', 'task_code', 'review_time',
        'assign_time', 'completed_time', 'cancelled_time'
    ]
