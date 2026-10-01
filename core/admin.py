from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User,Company,TenderCategory,Tender,TenderSubmission,Evaluation,ApprovalHistory,Notification,AuditLog
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets+(("TRMS",{"fields":("role",)}),)
    add_fieldsets=UserAdmin.add_fieldsets+(("TRMS",{"fields":("email","role")}),)
for model in [Company,TenderCategory,Tender,TenderSubmission,Evaluation,ApprovalHistory,Notification,AuditLog]:
    admin.site.register(model)
