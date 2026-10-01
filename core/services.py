from .models import AuditLog,Notification,User
from .security import client_ip

def audit(request,action,obj=None):
    AuditLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        action=action,
        target_type=obj.__class__.__name__ if obj else "",
        target_id=str(obj.pk) if obj and obj.pk else "",
        ip_address=client_ip(request),
    )

def notify_roles(roles,message):
    users=User.objects.filter(role__in=roles,is_active=True)
    Notification.objects.bulk_create([Notification(user=u,message=message) for u in users])

def notify_user(user,message):
    Notification.objects.create(user=user,message=message)
