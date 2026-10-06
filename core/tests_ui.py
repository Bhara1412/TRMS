"""Regression coverage for the existing nine functions after the UI redesign."""
from datetime import date, timedelta
from html.parser import HTMLParser
from tempfile import TemporaryDirectory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from .models import User, Company, TenderCategory, Tender, TenderSubmission, Evaluation, ApprovalHistory, Notification, AuditLog
from .test_documents import pdf_bytes


class FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = {}
        self.controls = []
        self.current = None
        self.invalid = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            if self.current:
                self.invalid = True
            self.current = attrs.get('id', 'anonymous')
            self.forms[self.current] = attrs
        if tag in ('input', 'select', 'button'):
            self.controls.append((attrs.get('name'), attrs.get('form', self.current), attrs))

    def handle_endtag(self, tag):
        if tag == 'form':
            self.current = None


class RedesignWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = {}
        for role in (User.Role.PROCUREMENT, User.Role.EVALUATION, User.Role.APPROVAL, User.Role.ADMIN):
            cls.staff[role] = User.objects.create_user(username=role.lower(), email=f'{role.lower()}@example.com', password='TestOnly!4382', role=role)
        cls.representative = User.objects.create_user(username='vendor', email='vendor@example.com', password='TestOnly!4382', role=User.Role.COMPANY)
        cls.company = Company.objects.create(representative=cls.representative, name='Test Company', registration_number='TEST-001', address='Test address', phone_number='0123456789', authorized_representative='Test Person', ssm_certificate='test.pdf', company_profile='test.pdf')
        cls.category = TenderCategory.objects.create(name='ICT Services')
        cls.tender = Tender.objects.create(title='Test tender', reference_no='TEST-T01', category=cls.category, description='Test scope', closing_date=date.today()+timedelta(days=30))

    def setUp(self):
        (__import__('pathlib').Path(__file__).resolve().parents[1] / 'test-tmp').mkdir(exist_ok=True)
        self.media = TemporaryDirectory(dir=__import__('pathlib').Path(__file__).resolve().parents[1] / 'test-tmp')
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.addCleanup(self.media.cleanup)
        self.addCleanup(self.settings_override.disable)

    def upload(self, name='test.pdf'):
        return SimpleUploadedFile(name, pdf_bytes(), content_type='application/pdf')

    def post_decision(self, url, data):
        response=self.client.get(url)
        if response.context and 'form' in response.context:
            data=dict(data, decision_token=response.context['form'].initial['decision_token'])
        return self.client.post(url,data)

    def as_role(self, role):
        self.client.force_login(self.representative if role == User.Role.COMPANY else self.staff[role])

    def submit(self):
        self.company.status = Company.Status.APPROVED
        self.company.save()
        self.as_role(User.Role.COMPANY)
        self.assertEqual(self.client.post(reverse('tender_submission'), {'tender':self.tender.pk, 'proposal':self.upload(), 'supporting_document':self.upload()}).status_code, 302)
        return TenderSubmission.objects.get(company=self.company, tender=self.tender)

    def evaluate(self, submission):
        self.as_role(User.Role.EVALUATION)
        self.assertEqual(self.client.get(reverse('tender_evaluation_detail', args=[submission.pk])).status_code,200)
        self.assertEqual(self.post_decision(reverse('tender_evaluation_detail', args=[submission.pk]), {'technical_score':85, 'financial_score':80, 'comments':'Meets criteria.'}).status_code,302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, TenderSubmission.Status.EVALUATED)

    def test_registration_and_login(self):
        self.assertContains(self.client.get(reverse('login')), 'Welcome back')
        self.assertContains(self.client.get(reverse('register_company')), 'Company registration')
        data = {'username':'newvendor', 'email':'newvendor@example.com', 'password1':'OrbitMaple!874321', 'password2':'OrbitMaple!874321', 'name':'New Vendor', 'registration_number':'TEST-NEW', 'address':'Company address', 'phone_number':'0123456789', 'authorized_representative':'New Person', 'ssm_certificate':self.upload(), 'company_profile':self.upload()}
        response = self.client.post(reverse('register_company'), data)
        self.assertEqual(response.status_code,302)
        company = Company.objects.get(registration_number='TEST-NEW')
        self.assertEqual(company.status, Company.Status.PENDING)
        self.assertTrue(Notification.objects.filter(user=self.staff[User.Role.PROCUREMENT]).exists())
        self.assertTrue(AuditLog.objects.filter(action='Company registration submitted').exists())
        self.client.post(reverse('logout'))
        self.assertEqual(self.client.post(reverse('login'), {'username':'newvendor','password':'OrbitMaple!874321'}).status_code,302)
        self.assertContains(self.client.get(reverse('dashboard')), 'New Vendor')

    def test_profile_review_submission_evaluation_and_sequential_approval(self):
        self.as_role(User.Role.COMPANY)
        self.assertContains(self.client.get(reverse('company_profile')), 'Pending Review')
        self.client.post(reverse('company_profile'), {'name':'Updated Company','address':'Updated address','phone_number':'0123456789','authorized_representative':'Updated Person'})
        self.company.refresh_from_db()
        self.assertEqual(self.company.name,'Updated Company')
        self.client.post(reverse('tender_submission'), {'tender':self.tender.pk,'proposal':self.upload()})
        self.assertEqual(TenderSubmission.objects.count(),0)
        self.as_role(User.Role.PROCUREMENT)
        self.assertContains(self.client.get(reverse('registration_review')),'Updated Company')
        self.assertContains(self.client.get(reverse('registration_review_detail',args=[self.company.pk])),'SSM certificate')
        self.post_decision(reverse('registration_review_detail',args=[self.company.pk]), {'decision':'APPROVED','comment':'Verified'})
        self.company.refresh_from_db()
        self.assertEqual(self.company.status,Company.Status.APPROVED)
        submission = self.submit()
        self.evaluate(submission)
        self.as_role(User.Role.APPROVAL)
        for level, expected in [(1,TenderSubmission.Status.LEVEL1),(2,TenderSubmission.Status.LEVEL2),(3,TenderSubmission.Status.APPROVED)]:
            url = reverse('approval_workflow_detail',args=[submission.pk])
            self.assertContains(self.client.get(url),f'Level {level} decision')
            self.assertEqual(self.post_decision(url, {'decision':'APPROVED','comment':f'Level {level} passed'}).status_code,302)
            submission.refresh_from_db()
            self.assertEqual(submission.status,expected)
            self.assertEqual(ApprovalHistory.objects.filter(submission=submission).count(),level)
        self.assertEqual(self.client.get(url).status_code,302)
        self.assertEqual(Evaluation.objects.filter(submission=submission).count(),1)
        self.assertTrue(Notification.objects.filter(user=self.representative, message__contains='Final Approved').exists())
        self.assertTrue(AuditLog.objects.filter(action='Approval Level 3: APPROVED').exists())

    def test_rejection_stops_approval_and_unevaluated_submission_cannot_advance(self):
        submission = self.submit()
        self.as_role(User.Role.APPROVAL)
        url = reverse('approval_workflow_detail',args=[submission.pk])
        self.client.post(url, {'decision':'APPROVED'})
        self.assertFalse(ApprovalHistory.objects.exists())
        self.evaluate(submission)
        self.as_role(User.Role.APPROVAL)
        self.post_decision(url, {'decision':'REJECTED','comment':'Does not meet criteria'})
        self.client.post(url, {'decision':'APPROVED'})
        submission.refresh_from_db()
        self.assertEqual(submission.status,TenderSubmission.Status.REJECTED)
        self.assertEqual(ApprovalHistory.objects.count(),1)

    def test_invalid_forms_keep_feedback_and_duplicate_submission_is_blocked(self):
        self.as_role(User.Role.COMPANY)
        response = self.client.post(reverse('company_profile'), {'name':'','address':'','phone_number':'','authorized_representative':''})
        self.assertContains(response,'This field is required.')
        submission=self.submit()
        self.client.post(reverse('tender_submission'), {'tender':self.tender.pk,'proposal':self.upload('bad.exe')})
        self.assertEqual(TenderSubmission.objects.count(),1)
        response=self.client.post(reverse('tender_submission'), {'tender':self.tender.pk,'proposal':self.upload()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(TenderSubmission.objects.count(),1)
        self.as_role(User.Role.EVALUATION)
        response=self.post_decision(reverse('tender_evaluation_detail',args=[submission.pk]), {'technical_score':101,'financial_score':80,'comments':'Test'})
        self.assertContains(response,'Ensure this value is less than or equal to 100.')
        self.assertFalse(Evaluation.objects.exists())

    def test_admin_forms_and_notification_ownership(self):
        self.as_role(User.Role.ADMIN)
        response=self.client.get(reverse('administration'))
        self.assertEqual(response.status_code,200)
        parser=FormParser(); parser.feed(response.content.decode())
        self.assertFalse(parser.invalid)
        for u in User.objects.all():
            form_id=f'user-{u.pk}'
            self.assertIn(form_id,parser.forms)
            self.assertTrue(any(name=='user-role' and form==form_id for name,form,attrs in parser.controls))
            self.assertTrue(any(name=='user-is_active' and form==form_id for name,form,attrs in parser.controls))
        self.client.post(reverse('administration'), {'action':'create_category','category-name':'Construction'})
        self.assertTrue(TenderCategory.objects.filter(name='Construction').exists())
        self.client.post(reverse('administration'), {'action':'create_tender','tender-title':'Second tender','tender-reference_no':'TEST-T02','tender-category':self.category.pk,'tender-description':'Test','tender-closing_date':(date.today()+timedelta(days=20)).isoformat(),'tender-is_open':'on'})
        self.assertTrue(Tender.objects.filter(reference_no='TEST-T02').exists())
        self.client.post(reverse('administration'), {'action':'update_user','user_id':self.staff[User.Role.EVALUATION].pk,'user-role':'EVALUATION'})
        self.staff[User.Role.EVALUATION].refresh_from_db()
        self.assertFalse(self.staff[User.Role.EVALUATION].is_active)
        mine=Notification.objects.create(user=self.representative,message='Company only')
        other=Notification.objects.create(user=self.staff[User.Role.PROCUREMENT],message='Officer only')
        self.as_role(User.Role.COMPANY)
        self.assertContains(self.client.get(reverse('audit_notifications')),'Company only')
        self.assertNotContains(self.client.get(reverse('audit_notifications')),'Officer only')
        self.client.post(reverse('mark_notifications_read'))
        mine.refresh_from_db(); other.refresh_from_db()
        self.assertTrue(mine.is_read); self.assertFalse(other.is_read)

    def test_role_access_navigation_and_post_only_security(self):
        pages={'company_profile':User.Role.COMPANY,'tender_submission':User.Role.COMPANY,'registration_review':User.Role.PROCUREMENT,'tender_evaluation':User.Role.EVALUATION,'approval_workflow':User.Role.APPROVAL,'administration':User.Role.ADMIN}
        for role in User.Role.values:
            self.as_role(role)
            self.assertEqual(self.client.get(reverse('dashboard')).status_code,200)
            for route, allowed in pages.items():
                self.assertEqual(self.client.get(reverse(route)).status_code,200 if role==allowed else 302)
            self.assertEqual(self.client.get(reverse('audit_notifications')).status_code,200)
        self.assertEqual(self.client.get(reverse('logout')).status_code,405)
        self.assertEqual(self.client.get(reverse('mark_notifications_read')).status_code,405)
        csrf_client=Client(enforce_csrf_checks=True)
        self.assertEqual(csrf_client.post(reverse('login'),{'username':'vendor','password':'TestOnly!4382'}).status_code,403)

