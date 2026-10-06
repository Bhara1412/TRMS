from django.contrib import messages
from django.contrib.auth import login,logout
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError,OperationalError,transaction
from django.utils import timezone
from .hardening import decision_token, valid_decision, advance, StaleDecision, login_is_limited, record_login
from django.shortcuts import get_object_or_404,redirect,render
from django.views.decorators.http import require_POST
from .forms import ApprovalForm,AdminUserForm,CompanyProfileForm,CompanyRegistrationForm,EvaluationForm,ReviewForm,SecureAuthenticationForm,TenderCategoryForm,TenderForm,TenderSubmissionForm
from .models import ApprovalHistory,AuditLog,Company,Notification,Tender,TenderCategory,TenderSubmission,User
from .security import role_required
from .services import audit,notify_roles,notify_user

def home(request):
    return redirect("dashboard") if request.user.is_authenticated else redirect("login")

# FR-02 Authentication
def login_view(request):
    if request.user.is_authenticated: return redirect("dashboard")
    form=SecureAuthenticationForm(request,data=request.POST or None)
    if request.method=="POST":
        identifier=request.POST.get('username', '').strip()[:254]
        # Normalise the email alias to the same throttle key as its username.
        canonical=User.objects.filter(username=identifier).first()
        if canonical is None and '@' in identifier:
            matches=User.objects.filter(email__iexact=identifier)
            if matches.count() == 1: canonical=matches.first()
        account=canonical.username if canonical else identifier
        if login_is_limited(request, account):
            form.add_error(None, 'Too many attempts. Please wait 15 minutes before trying again.')
            response=render(request, "core/login.html", {"form":form}, status=429)
            response['Retry-After']='900'
            return response
        if form.is_valid():
            login(request,form.get_user())
            record_login(request, account, success=True)
            audit(request,"Successful login")
            return redirect("dashboard")
        record_login(request, account)
        messages.error(request,"Invalid username or password.")
    return render(request,"core/login.html",{"form":form})

@require_POST
@login_required
def logout_view(request):
    audit(request,"Logout")
    logout(request)
    return redirect("login")

# FR-01 Company Registration
def register_company(request):
    if request.user.is_authenticated: return redirect("dashboard")
    form=CompanyRegistrationForm(request.POST or None,request.FILES or None)
    if request.method=="POST" and form.is_valid():
        try:
            with transaction.atomic():
                user=form.save(commit=False)
                user.email=form.cleaned_data["email"]
                user.role=User.Role.COMPANY
                user.save()
                company=Company.objects.create(
                    representative=user,name=form.cleaned_data["name"],
                    registration_number=form.cleaned_data["registration_number"],
                    address=form.cleaned_data["address"],phone_number=form.cleaned_data["phone_number"],
                    authorized_representative=form.cleaned_data["authorized_representative"],
                    ssm_certificate=form.cleaned_data["ssm_certificate"],company_profile=form.cleaned_data["company_profile"])
                notify_roles([User.Role.PROCUREMENT],f"New company registration awaiting review: {company.name}")
                login(request,user)
                audit(request,"Company registration submitted",company)
                messages.success(request,"Registration submitted. Procurement review is required before tender submission.")
                return redirect("dashboard")
        except IntegrityError:
            form.add_error(None,"Username, email or company registration number already exists.")
    return render(request,"core/register.html",{"form":form})

@login_required
def dashboard(request):
    context={"my_notifications":Notification.objects.filter(user=request.user).order_by("-created_at")[:5]}
    if request.user.role==User.Role.COMPANY:
        context["company"]=Company.objects.filter(representative=request.user).first()
        context["my_submissions"]=TenderSubmission.objects.filter(company__representative=request.user).select_related("tender")
    elif request.user.role==User.Role.PROCUREMENT:
        context["pending_registrations"]=Company.objects.filter(status=Company.Status.PENDING).count()
    elif request.user.role==User.Role.EVALUATION:
        context["pending_evaluations"]=TenderSubmission.objects.filter(status=TenderSubmission.Status.SUBMITTED).count()
    elif request.user.role==User.Role.APPROVAL:
        context["approval_ready"]=TenderSubmission.objects.filter(status__in=[TenderSubmission.Status.EVALUATED,TenderSubmission.Status.LEVEL1,TenderSubmission.Status.LEVEL2]).count()
    return render(request,"core/dashboard.html",context)

# FR-03 Company Profile
@role_required(User.Role.COMPANY)
def company_profile(request):
    company=get_object_or_404(Company,representative=request.user)
    form=CompanyProfileForm(request.POST or None,instance=company)
    if request.method=="POST" and form.is_valid():
        form.save(); audit(request,"Company profile updated",company)
        messages.success(request,"Company profile updated."); return redirect("company_profile")
    return render(request,"core/company_profile.html",{"form":form,"company":company})

# FR-04 Tender Submission
@role_required(User.Role.COMPANY)
def tender_submission(request):
    company=get_object_or_404(Company,representative=request.user)
    submissions=TenderSubmission.objects.filter(company=company).select_related("tender")
    form=TenderSubmissionForm(request.POST or None,request.FILES or None)
    form.fields["tender"].queryset=Tender.objects.filter(is_open=True)
    if request.method=="POST":
        if company.status != Company.Status.APPROVED:
            messages.error(request,"Your company must be approved before submitting a tender.")
        elif form.is_valid():
            try:
                with transaction.atomic():
                    s=form.save(commit=False); s.company=company; s.save()
                    notify_roles([User.Role.EVALUATION],f"New tender submission awaiting evaluation: {s}")
                    audit(request,"Tender submitted",s)
                messages.success(request,"Tender submitted successfully."); return redirect("tender_submission")
            except IntegrityError:
                form.add_error(None,"Your company has already submitted for this tender.")
    return render(request,"core/tender_submission.html",{"form":form,"submissions":submissions,"company":company})

# FR-05 Registration Review
@role_required(User.Role.PROCUREMENT)
def registration_review(request,company_id=None):
    if company_id is None:
        return render(request,"core/registration_review_list.html",{"companies":Company.objects.filter(status=Company.Status.PENDING)})
    company=get_object_or_404(Company,pk=company_id)
    if company.status != Company.Status.PENDING:
        messages.info(request,"This registration has already been reviewed.")
        return redirect("registration_review")
    form=ReviewForm(request.POST or None, initial={'decision_token':decision_token(request, company, 'review')})
    if request.method=="POST" and form.is_valid():
        if not valid_decision(request, company, 'review', form.cleaned_data['decision_token']):
            form.add_error(None, 'This review is stale or invalid. Reload the page.')
        else:
            try:
                with transaction.atomic():
                    advance(Company, company, form.cleaned_data['decision'], review_comment=form.cleaned_data['comment'], updated_at=timezone.now())
                    notify_user(company.representative,f"Company registration status: {company.get_status_display()}.")
                    audit(request,f"Company registration {company.status.lower()}",company)
                messages.success(request,"Registration decision recorded.")
                return redirect("registration_review")
            except (StaleDecision, IntegrityError, OperationalError):
                form.add_error(None, 'The decision could not be saved. Reload the page before retrying.')
    return render(request,"core/registration_review_detail.html",{"company":company,"form":form})

# FR-06 Tender Evaluation
@role_required(User.Role.EVALUATION)
def tender_evaluation(request,submission_id=None):
    if submission_id is None:
        subs=TenderSubmission.objects.filter(status=TenderSubmission.Status.SUBMITTED).select_related("company","tender")
        return render(request,"core/evaluation_list.html",{"submissions":subs})
    s=get_object_or_404(TenderSubmission,pk=submission_id,status=TenderSubmission.Status.SUBMITTED)
    form=EvaluationForm(request.POST or None, initial={'decision_token':decision_token(request, s, 'evaluation')})
    if request.method=="POST" and form.is_valid():
        if not valid_decision(request, s, 'evaluation', form.cleaned_data['decision_token']):
            form.add_error(None, 'This evaluation is stale or invalid. Reload the page.')
        else:
            try:
                with transaction.atomic():
                    advance(TenderSubmission, s, TenderSubmission.Status.EVALUATED)
                    e=form.save(commit=False); e.submission=s; e.evaluator=request.user; e.save()
                    notify_roles([User.Role.APPROVAL],f"Submission {s.id} is ready for Level 1 approval.")
                    notify_user(s.company.representative,f"Tender {s.tender.reference_no} has been evaluated.")
                    audit(request,"Tender evaluated",s)
                messages.success(request,"Evaluation completed.")
                return redirect("tender_evaluation")
            except (StaleDecision, IntegrityError, OperationalError):
                form.add_error(None, 'The evaluation could not be saved. Reload the page before retrying.')
    return render(request,"core/evaluation_detail.html",{"submission":s,"form":form})

# FR-07 Approval Workflow
@role_required(User.Role.APPROVAL)
def approval_workflow(request,submission_id=None):
    if submission_id is None:
        qs=TenderSubmission.objects.filter(status__in=[TenderSubmission.Status.EVALUATED,TenderSubmission.Status.LEVEL1,TenderSubmission.Status.LEVEL2]).select_related("company","tender")
        return render(request,"core/approval_list.html",{"submissions":qs})
    s=get_object_or_404(TenderSubmission,pk=submission_id)
    level={TenderSubmission.Status.EVALUATED:1,TenderSubmission.Status.LEVEL1:2,TenderSubmission.Status.LEVEL2:3}.get(s.status)
    if not level:
        messages.error(request,"This submission is not currently eligible for approval.")
        return redirect("approval_workflow")
    form=ApprovalForm(request.POST or None, initial={'decision_token':decision_token(request, s, 'approval')})
    if request.method=="POST" and form.is_valid():
        if not valid_decision(request, s, 'approval', form.cleaned_data['decision_token']):
            form.add_error(None, 'This approval is stale or invalid. Reload the page.')
        else:
            decision=form.cleaned_data['decision']
            next_status=TenderSubmission.Status.REJECTED if decision==ApprovalHistory.Decision.REJECTED else {1:TenderSubmission.Status.LEVEL1,2:TenderSubmission.Status.LEVEL2,3:TenderSubmission.Status.APPROVED}[level]
            try:
                with transaction.atomic():
                    advance(TenderSubmission, s, next_status)
                    ApprovalHistory.objects.create(submission=s,approver=request.user,level=level,decision=decision,comment=form.cleaned_data['comment'])
                    notify_user(s.company.representative,f"Tender {s.tender.reference_no}: {s.get_status_display()}.")
                    audit(request,f"Approval Level {level}: {decision}",s)
                messages.success(request,f"Level {level} decision recorded.")
                return redirect("approval_workflow")
            except (StaleDecision, IntegrityError, OperationalError):
                form.add_error(None, 'The approval could not be saved. Reload the page before retrying.')
    return render(request,"core/approval_detail.html",{"submission":s,"form":form,"level":level})

# FR-08 Administration
@role_required(User.Role.ADMIN)
def administration(request):
    users=User.objects.all().order_by("username"); tenders=Tender.objects.all().select_related("category"); categories=TenderCategory.objects.all()
    user_form=AdminUserForm(prefix="user"); tender_form=TenderForm(prefix="tender"); category_form=TenderCategoryForm(prefix="category")
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="update_user":
            u=get_object_or_404(User,pk=request.POST.get("user_id"))
            user_form=AdminUserForm(request.POST,instance=u,prefix="user")
            if user_form.is_valid():
                user_form.save(); audit(request,"User role/status updated",u); messages.success(request,"User updated."); return redirect("administration")
        elif action=="create_tender":
            tender_form=TenderForm(request.POST,prefix="tender")
            if tender_form.is_valid():
                t=tender_form.save(); audit(request,"Tender created",t); messages.success(request,"Tender created."); return redirect("administration")
        elif action=="create_category":
            category_form=TenderCategoryForm(request.POST,prefix="category")
            if category_form.is_valid():
                c=category_form.save(); audit(request,"Tender category created",c); messages.success(request,"Category created."); return redirect("administration")
    return render(request,"core/administration.html",{"users":users,"tenders":tenders,"categories":categories,"user_form":user_form,"tender_form":tender_form,"category_form":category_form})

# FR-09 Audit & Notification
@login_required
def audit_notifications(request):
    notifications=Notification.objects.filter(user=request.user).order_by("-created_at")
    logs=AuditLog.objects.select_related("user")[:200] if request.user.role==User.Role.ADMIN else AuditLog.objects.filter(user=request.user)[:100]
    return render(request,"core/audit_notifications.html",{"notifications":notifications,"logs":logs})

@require_POST
@login_required
def mark_notifications_read(request):
    Notification.objects.filter(user=request.user,is_read=False).update(is_read=True)
    audit(request,"Notifications marked as read")
    return redirect("audit_notifications")
