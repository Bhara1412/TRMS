import os, uuid
from django.contrib.auth.models import AbstractUser
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.db import models

def secure_upload_path(instance, filename):
    ext=os.path.splitext(filename)[1].lower()
    return f"documents/{uuid.uuid4().hex}{ext}"

class User(AbstractUser):
    class Role(models.TextChoices):
        COMPANY="COMPANY","Company Representative"
        PROCUREMENT="PROCUREMENT","Procurement Officer"
        EVALUATION="EVALUATION","Evaluation Officer"
        APPROVAL="APPROVAL","Approval Committee"
        ADMIN="ADMIN","System Administrator"
    email=models.EmailField(unique=True)
    role=models.CharField(max_length=20,choices=Role.choices,default=Role.COMPANY)
    def __str__(self): return f"{self.username} ({self.get_role_display()})"

class Company(models.Model):
    class Status(models.TextChoices):
        PENDING="PENDING","Pending Review"
        APPROVED="APPROVED","Approved"
        REJECTED="REJECTED","Rejected"
    representative=models.OneToOneField(User,on_delete=models.PROTECT,related_name="company")
    name=models.CharField(max_length=200)
    registration_number=models.CharField(max_length=100,unique=True)
    address=models.TextField()
    phone_number=models.CharField(max_length=30)
    authorized_representative=models.CharField(max_length=200)
    ssm_certificate=models.FileField(upload_to=secure_upload_path,validators=[FileExtensionValidator(["pdf","doc","docx"])])
    company_profile=models.FileField(upload_to=secure_upload_path,validators=[FileExtensionValidator(["pdf","doc","docx"])])
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.PENDING)
    review_comment=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)
    def __str__(self): return self.name

class TenderCategory(models.Model):
    name=models.CharField(max_length=120,unique=True)
    def __str__(self): return self.name

class Tender(models.Model):
    title=models.CharField(max_length=200)
    reference_no=models.CharField(max_length=80,unique=True)
    category=models.ForeignKey(TenderCategory,on_delete=models.PROTECT)
    description=models.TextField()
    closing_date=models.DateField()
    is_open=models.BooleanField(default=True)
    def __str__(self): return f"{self.reference_no} - {self.title}"

class TenderSubmission(models.Model):
    class Status(models.TextChoices):
        SUBMITTED="SUBMITTED","Submitted"
        EVALUATED="EVALUATED","Evaluated"
        LEVEL1="LEVEL1","Level 1 Approved"
        LEVEL2="LEVEL2","Level 2 Approved"
        APPROVED="APPROVED","Final Approved"
        REJECTED="REJECTED","Rejected"
    company=models.ForeignKey(Company,on_delete=models.PROTECT,related_name="submissions")
    tender=models.ForeignKey(Tender,on_delete=models.PROTECT,related_name="submissions")
    proposal=models.FileField(upload_to=secure_upload_path,validators=[FileExtensionValidator(["pdf","doc","docx"])])
    supporting_document=models.FileField(upload_to=secure_upload_path,validators=[FileExtensionValidator(["pdf","doc","docx"])],blank=True)
    status=models.CharField(max_length=20,choices=Status.choices,default=Status.SUBMITTED)
    submitted_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["company","tender"],name="one_submission_per_company_tender")]
    def __str__(self): return f"{self.company} -> {self.tender}"

class Evaluation(models.Model):
    submission=models.OneToOneField(TenderSubmission,on_delete=models.CASCADE,related_name="evaluation")
    evaluator=models.ForeignKey(User,on_delete=models.PROTECT)
    technical_score=models.PositiveIntegerField(validators=[MinValueValidator(0),MaxValueValidator(100)])
    financial_score=models.PositiveIntegerField(validators=[MinValueValidator(0),MaxValueValidator(100)])
    comments=models.TextField()
    evaluated_at=models.DateTimeField(auto_now_add=True)

class ApprovalHistory(models.Model):
    class Decision(models.TextChoices):
        APPROVED="APPROVED","Approved"
        REJECTED="REJECTED","Rejected"
    submission=models.ForeignKey(TenderSubmission,on_delete=models.CASCADE,related_name="approvals")
    approver=models.ForeignKey(User,on_delete=models.PROTECT)
    level=models.PositiveSmallIntegerField(validators=[MinValueValidator(1),MaxValueValidator(3)])
    decision=models.CharField(max_length=10,choices=Decision.choices)
    comment=models.TextField(blank=True)
    decided_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=["submission","level"],name="one_decision_per_level")]

class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE,related_name="notifications")
    message=models.TextField()
    is_read=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)

class AuditLog(models.Model):
    user=models.ForeignKey(User,on_delete=models.SET_NULL,null=True,blank=True)
    action=models.CharField(max_length=255)
    target_type=models.CharField(max_length=80,blank=True)
    target_id=models.CharField(max_length=80,blank=True)
    ip_address=models.GenericIPAddressField(null=True,blank=True)
    timestamp=models.DateTimeField(auto_now_add=True)
    class Meta: ordering=["-timestamp"]
