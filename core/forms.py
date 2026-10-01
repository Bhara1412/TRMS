from pathlib import Path
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Company,TenderSubmission,Evaluation,User,Tender,TenderCategory

ALLOWED_EXTENSIONS={".pdf",".doc",".docx"}
MAX_FILE_SIZE=5*1024*1024

def validate_upload(f):
    if not f: return f
    if Path(f.name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise forms.ValidationError("Only PDF, DOC and DOCX files are allowed.")
    if f.size > MAX_FILE_SIZE:
        raise forms.ValidationError("File must not exceed 5 MB.")
    return f

class SecureAuthenticationForm(AuthenticationForm):
    username=forms.CharField(widget=forms.TextInput(attrs={"class":"form-control","autocomplete":"username"}))
    password=forms.CharField(widget=forms.PasswordInput(attrs={"class":"form-control","autocomplete":"current-password"}))

class CompanyRegistrationForm(UserCreationForm):
    email=forms.EmailField()
    name=forms.CharField(max_length=200)
    registration_number=forms.CharField(max_length=100)
    address=forms.CharField(widget=forms.Textarea(attrs={"rows":3}))
    phone_number=forms.CharField(max_length=30)
    authorized_representative=forms.CharField(max_length=200)
    ssm_certificate=forms.FileField()
    company_profile=forms.FileField()
    class Meta:
        model=User
        fields=["username","email","password1","password2"]
    def clean_ssm_certificate(self): return validate_upload(self.cleaned_data["ssm_certificate"])
    def clean_company_profile(self): return validate_upload(self.cleaned_data["company_profile"])

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model=Company
        fields=["name","address","phone_number","authorized_representative"]

class TenderSubmissionForm(forms.ModelForm):
    class Meta:
        model=TenderSubmission
        fields=["tender","proposal","supporting_document"]
    def clean_proposal(self): return validate_upload(self.cleaned_data["proposal"])
    def clean_supporting_document(self):
        f=self.cleaned_data.get("supporting_document")
        return validate_upload(f) if f else f

class EvaluationForm(forms.ModelForm):
    class Meta:
        model=Evaluation
        fields=["technical_score","financial_score","comments"]

class ReviewForm(forms.Form):
    decision=forms.ChoiceField(choices=[("APPROVED","Approve"),("REJECTED","Reject")])
    comment=forms.CharField(widget=forms.Textarea(attrs={"rows":3}),required=False)

class ApprovalForm(forms.Form):
    decision=forms.ChoiceField(choices=[("APPROVED","Approve"),("REJECTED","Reject")])
    comment=forms.CharField(widget=forms.Textarea(attrs={"rows":3}),required=False)

class AdminUserForm(forms.ModelForm):
    class Meta:
        model=User
        fields=["role","is_active"]

class TenderForm(forms.ModelForm):
    class Meta:
        model=Tender
        fields=["title","reference_no","category","description","closing_date","is_open"]
        widgets={"closing_date":forms.DateInput(attrs={"type":"date"})}

class TenderCategoryForm(forms.ModelForm):
    class Meta:
        model=TenderCategory
        fields=["name"]
