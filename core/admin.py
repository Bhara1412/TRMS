from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User,Company,TenderCategory,Tender,TenderSubmission,Evaluation,ApprovalHistory,Notification,AuditLog

class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and request.user.role == User.Role.ADMIN

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets+(("TRMS",{"fields":("role",)}),)
    add_fieldsets=UserAdmin.add_fieldsets+(("TRMS",{"fields":("email","role")}),)
    def has_delete_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
    def has_add_permission(self, request): return False
    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser and request.user.role == User.Role.ADMIN

# Domain records can only be changed through the audited TRMS workflows.
for model in [Company,TenderCategory,Tender,TenderSubmission,Evaluation,ApprovalHistory,Notification,AuditLog]:
    admin.site.register(model, ReadOnlyAdmin)
