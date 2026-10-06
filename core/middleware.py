"""Apply the same login protection to Django's administrative login."""
from django.http import HttpResponse
from .hardening import canonical_identifier, login_is_limited, record_login

class AdminLoginThrottleMiddleware:
    def __init__(self, get_response): self.get_response=get_response
    def __call__(self, request):
        is_login=request.method=='POST' and request.path_info.rstrip('/')=='/django-admin/login'
        account=None
        if is_login:
            account=canonical_identifier(request.POST.get('username','').strip()[:254])
            if login_is_limited(request,account):
                response=HttpResponse('Too many attempts. Please wait 15 minutes before trying again.',status=429)
                response['Retry-After']='900'
                return response
        response=self.get_response(request)
        if is_login and response.status_code in (200,302):
            record_login(request,account,success=request.user.is_authenticated and response.status_code==302)
        return response
