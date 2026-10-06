from pathlib import Path
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import Company,TenderSubmission,Evaluation,User,Tender,TenderCategory

from .uploads import validate_upload

class SecureAuthenticationForm(AuthenticationForm):
    def clean(self):
        identifier = self.cleaned_data.get('username', '').strip()
        if '@' in identifier and not User.objects.filter(username=identifier).exists():
            matches = User.objects.filter(email__iexact=identifier)
            if matches.count() == 1:
                self.cleaned_data['username'] = matches.first().username
        return super().clean()

    username=forms.CharField(label="Username or email", widget=forms.TextInput(attrs={"class":"form-control","autocomplete":"username"}))
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
    def clean_email(self):
        value = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError('This email address is already registered.')
        return value
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
    decision_token=forms.CharField(widget=forms.HiddenInput)
    class Meta:
        model=Evaluation
        fields=["technical_score","financial_score","comments"]

class ReviewForm(forms.Form):
    decision_token=forms.CharField(widget=forms.HiddenInput)
    decision=forms.ChoiceField(choices=[("APPROVED","Approve"),("REJECTED","Reject")])
    comment=forms.CharField(widget=forms.Textarea(attrs={"rows":3}),required=False)

class ApprovalForm(forms.Form):
    decision_token=forms.CharField(widget=forms.HiddenInput)
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
