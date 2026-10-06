"""Private document access within FR-03, FR-05, FR-06 and FR-07."""
from pathlib import Path
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from .models import Company, TenderSubmission, User
from .services import audit


@require_GET
@login_required
def document_download(request, kind, object_id, field_name):
    if kind == 'company' and field_name in {'ssm_certificate', 'company_profile'}:
        obj = get_object_or_404(Company, pk=object_id)
        owner = obj.representative_id
        allowed = {User.Role.PROCUREMENT, User.Role.ADMIN}
    elif kind == 'submission' and field_name in {'proposal', 'supporting_document'}:
        obj = get_object_or_404(TenderSubmission.objects.select_related('company'), pk=object_id)
        owner = obj.company.representative_id
        allowed = {User.Role.EVALUATION, User.Role.APPROVAL, User.Role.ADMIN}
    else:
        raise Http404
    if not (request.user.pk == owner and request.user.role == User.Role.COMPANY) and request.user.role not in allowed:
        raise Http404
    document = getattr(obj, field_name)
    if not document:
        raise Http404
    try:
        stream = document.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(stream, as_attachment=True, filename=f'{field_name}-{obj.pk}{Path(document.name).suffix.lower()}')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "sandbox; default-src 'none'"
    audit(request, 'Private document downloaded', obj)
    return response
