from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

def role_required(*allowed_roles):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request,*args,**kwargs):
            if request.user.role not in allowed_roles:
                from .services import audit
                audit(request, "Role access denied")
                messages.error(request,"You are not authorised to access that function.")
                return redirect("dashboard")
            return view_func(request,*args,**kwargs)
        return wrapper
    return decorator

def client_ip(request):
    from .hardening import peer_ip
    return peer_ip(request)
