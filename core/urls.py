from django.urls import path
from . import views
urlpatterns=[
    path("",views.home,name="home"),
    path("login/",views.login_view,name="login"),
    path("logout/",views.logout_view,name="logout"),
    path("register/",views.register_company,name="register_company"),
    path("dashboard/",views.dashboard,name="dashboard"),
    path("company/profile/",views.company_profile,name="company_profile"),
    path("tenders/submit/",views.tender_submission,name="tender_submission"),
    path("registrations/review/",views.registration_review,name="registration_review"),
    path("registrations/review/<int:company_id>/",views.registration_review,name="registration_review_detail"),
    path("evaluations/",views.tender_evaluation,name="tender_evaluation"),
    path("evaluations/<int:submission_id>/",views.tender_evaluation,name="tender_evaluation_detail"),
    path("approvals/",views.approval_workflow,name="approval_workflow"),
    path("approvals/<int:submission_id>/",views.approval_workflow,name="approval_workflow_detail"),
    path("administration/",views.administration,name="administration"),
    path("audit-notifications/",views.audit_notifications,name="audit_notifications"),
    path("audit-notifications/read/",views.mark_notifications_read,name="mark_notifications_read"),
]
