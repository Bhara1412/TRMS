"""Security controls shared by the existing authentication and decision workflows."""
import ipaddress
from datetime import timedelta
from django.core import signing
from django.utils import timezone
from django.utils.crypto import salted_hmac
from .models import AuditLog, User

LOGIN_WINDOW_SECONDS = 900
LOGIN_ACCOUNT_LIMIT = 5
LOGIN_IP_LIMIT = 30


def peer_ip(request):
    # Proxy headers are untrusted unless a deployment explicitly configures a proxy.
    try:
        return str(ipaddress.ip_address(request.META.get('REMOTE_ADDR', '')))
    except ValueError:
        return None


def login_fingerprint(identifier):
    return salted_hmac('trms.authentication', identifier.strip().casefold()).hexdigest()


def canonical_identifier(identifier):
    user=User.objects.filter(username=identifier).first()
    if user is None and '@' in identifier:
        matches=User.objects.filter(email__iexact=identifier)
        if matches.count()==1: user=matches.first()
    return user.username if user else identifier


def login_is_limited(request, identifier):
    recent = AuditLog.objects.filter(
        target_type='Authentication', timestamp__gte=timezone.now()-timedelta(seconds=LOGIN_WINDOW_SECONDS)
    )
    fingerprint = login_fingerprint(identifier)
    last_success = recent.filter(action='Authentication succeeded', target_id=fingerprint).order_by('-timestamp').first()
    failures = recent.filter(action='Failed login')
    account_failures = failures.filter(target_id=fingerprint)
    if last_success:
        account_failures = account_failures.filter(timestamp__gt=last_success.timestamp)
    return account_failures.count() >= LOGIN_ACCOUNT_LIMIT or failures.filter(ip_address=peer_ip(request)).count() >= LOGIN_IP_LIMIT


def record_login(request, identifier, success=False):
    AuditLog.objects.create(
        user=request.user if success and request.user.is_authenticated else None,
        action='Authentication succeeded' if success else 'Failed login',
        target_type='Authentication', target_id=login_fingerprint(identifier), ip_address=peer_ip(request),
    )


def decision_token(request, obj, kind):
    return signing.dumps({'user': request.user.pk, 'object': obj.pk, 'status': obj.status, 'kind': kind}, salt='trms.decision')


def valid_decision(request, obj, kind, token):
    try:
        data = signing.loads(token, salt='trms.decision', max_age=1800)
    except signing.BadSignature:
        return False
    return data == {'user': request.user.pk, 'object': obj.pk, 'status': obj.status, 'kind': kind}


class StaleDecision(Exception):
    pass


def advance(model, obj, next_status, **extra):
    """One conditional UPDATE claims the current stage before history is written.

    Run inside the caller's atomic block; an error rolls back the claim and history.
    This also works with SQLite, whose select_for_update() does not lock rows.
    """
    changed = model.objects.filter(pk=obj.pk, status=obj.status).update(status=next_status, **extra)
    if changed != 1:
        raise StaleDecision('The record changed. Reload it before deciding.')
    obj.status = next_status
