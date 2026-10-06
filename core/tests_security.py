"""Adversarial checks for the security controls, alongside workflow regressions."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, TransactionTestCase, Client, override_settings
from django.urls import reverse
from .hardening import advance, StaleDecision
from .models import User, Company, Tender, TenderCategory, TenderSubmission, ApprovalHistory, AuditLog
from .uploads import validate_upload
from .test_documents import pdf_bytes, docx_bytes


class SecurityHardeningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users={}
        for role in User.Role.values:
            cls.users[role]=User.objects.create_user(username=role.lower(),email=f'{role.lower()}@example.test',password='SecurityOnly!3842',role=role,is_staff=role=='ADMIN',is_superuser=role=='ADMIN')
        cls.outsider=User.objects.create_user(username='other',email='other@example.test',password='OtherOnly!3824',role='COMPANY')
        cls.category=TenderCategory.objects.create(name='Test category')
        cls.tender=Tender.objects.create(title='Test tender',reference_no='SEC-01',category=cls.category,description='Scope',closing_date=date.today()+timedelta(days=10))

    def setUp(self):
        directory=Path(__file__).resolve().parents[1]/'test-tmp'; directory.mkdir(exist_ok=True)
        self.temp=TemporaryDirectory(dir=directory)
        override=override_settings(MEDIA_ROOT=self.temp.name)
        override.enable(); self.addCleanup(override.disable); self.addCleanup(self.temp.cleanup)
        self.company=Company.objects.create(representative=self.users['COMPANY'],name='Security fixture',registration_number='SEC-C01',address='Test address',phone_number='0123',authorized_representative='Test',status='APPROVED',ssm_certificate=self.file(),company_profile=self.file())
        self.submission=TenderSubmission.objects.create(company=self.company,tender=self.tender,proposal=self.file(),status='EVALUATED')

    def file(self, data=None, name='fixture.pdf'):
        return SimpleUploadedFile(name,pdf_bytes() if data is None else data)

    def test_document_permission_matrix_and_public_media_is_disabled(self):
        company_url=reverse('document_download',args=['company',self.company.pk,'ssm_certificate'])
        submission_url=reverse('document_download',args=['submission',self.submission.pk,'proposal'])
        self.assertEqual(self.client.get(company_url).status_code,302)
        self.assertEqual(self.client.get(submission_url).status_code,302)
        self.assertEqual(self.client.get('/media/'+self.submission.proposal.name).status_code,404)
        for role,user in self.users.items():
            self.client.force_login(user)
            for url,allowed in [(company_url,{'COMPANY','PROCUREMENT','ADMIN'}),(submission_url,{'COMPANY','EVALUATION','APPROVAL','ADMIN'})]:
                response=self.client.get(url)
                self.assertEqual(response.status_code,200 if role in allowed else 404)
                if response.status_code==200:
                    self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
                    self.assertEqual(response['Cache-Control'],'private, no-store')
                    response.close()
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(company_url).status_code,404)
        self.assertEqual(self.client.get(submission_url).status_code,404)
        self.assertEqual(self.client.get(reverse('document_download',args=['company',self.company.pk,'representative'])).status_code,404)
        self.assertEqual(self.client.get(reverse('document_download',args=['submission',self.submission.pk,'supporting_document'])).status_code,404)

    def test_login_throttle_blocks_password_and_email_alias_bypass(self):
        for i in range(5):
            self.assertEqual(self.client.post(reverse('login'),{'username':'company','password':'wrong'}).status_code,200)
        response=self.client.post(reverse('login'),{'username':'COMPANY@example.test','password':'SecurityOnly!3842'})
        self.assertEqual(response.status_code,429)
        self.assertNotIn('_auth_user_id',self.client.session)
        self.assertEqual(AuditLog.objects.filter(action='Failed login').count(),5)
        AuditLog.objects.filter(action='Failed login').update(timestamp=__import__('django.utils.timezone',fromlist=['now']).now()-timedelta(seconds=901))
        self.assertEqual(self.client.post(reverse('login'),{'username':'company@example.test','password':'SecurityOnly!3842'}).status_code,302)

    def test_ip_limit_cannot_be_bypassed_with_forwarded_header(self):
        for i in range(30):
            AuditLog.objects.create(action='Failed login',target_type='Authentication',target_id=str(i),ip_address='127.0.0.1')
        self.assertEqual(self.client.post(reverse('login'),{'username':'admin','password':'SecurityOnly!3842'},HTTP_X_FORWARDED_FOR='192.0.2.50').status_code,429)

    def test_admin_login_cannot_bypass_main_login_limit(self):
        for i in range(5):
            self.client.post(reverse('login'),{'username':'admin','password':'wrong'})
        self.assertEqual(self.client.post(reverse('admin:login'),{'username':'admin','password':'SecurityOnly!3842'}).status_code,429)

    def test_failed_admin_logins_are_limited_and_logged(self):
        for i in range(5):
            self.assertEqual(self.client.post(reverse('admin:login'),{'username':'admin','password':'wrong'}).status_code,200)
        self.assertEqual(self.client.post(reverse('admin:login'),{'username':'admin','password':'SecurityOnly!3842'}).status_code,429)
        self.assertEqual(AuditLog.objects.filter(action='Failed login').count(),5)

    def test_disguised_and_active_documents_are_rejected(self):
        for data,name in [(b'<script>alert(1)</script>','fake.pdf'),(b'%PDF-1.4 incomplete','broken.pdf'),(pdf_bytes().replace(b'/Type /Catalog',b'/Type /Catalog /J#61vaScript (alert)'), 'active.pdf'),(b'PK not a Word package','fake.docx'),(docx_bytes({'word/vbaProject.bin':b'payload'}),'macro.docx'),(docx_bytes({'../escape.txt':b'payload'}),'traversal.docx'),(docx_bytes({'word/embeddings/payload.bin':b'payload'}),'embedded.docx'),(b'not word','fake.doc')]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validate_upload(self.file(data,name))
        for data,name in [(pdf_bytes(),'valid.pdf'),(docx_bytes(),'valid.docx')]:
            upload=self.file(data,name)
            self.assertIs(validate_upload(upload),upload)
            self.assertEqual(upload.tell(),0)

    def test_docx_archive_expansion_and_xml_entities_are_rejected(self):
        for extra in [{'padding.txt':b'0'*(26*1024*1024)},{'word/other.xml':b'<!DOCTYPE x [<!ENTITY a "data">]><x>&a;</x>'},{'word/_rels/document.xml.rels':b'<Relationships><Relationship TargetMode="External" Type="image" Target="https://example.test/track"/></Relationships>'}]:
            with self.assertRaises(ValidationError): validate_upload(self.file(docx_bytes(extra),'unsafe.docx'))

    def token(self,url):
        return self.client.get(url).context['form'].initial['decision_token']

    def test_stale_double_submission_cannot_approve_two_levels(self):
        self.client.force_login(self.users['APPROVAL'])
        url=reverse('approval_workflow_detail',args=[self.submission.pk])
        data={'decision':'APPROVED','comment':'Reviewed','decision_token':self.token(url)}
        self.assertEqual(self.client.post(url,data).status_code,302)
        self.assertEqual(self.client.post(url,data).status_code,200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,'LEVEL1')
        self.assertEqual(ApprovalHistory.objects.count(),1)

    def test_missing_tampered_and_other_user_tokens_cannot_approve(self):
        self.client.force_login(self.users['APPROVAL'])
        url=reverse('approval_workflow_detail',args=[self.submission.pk])
        token=self.token(url)
        self.assertEqual(self.client.post(url,{'decision':'APPROVED'}).status_code,200)
        self.assertEqual(self.client.post(url,{'decision':'APPROVED','decision_token':token+'x'}).status_code,200)
        another=User.objects.create_user(username='approver2',email='approver2@example.test',password='AnotherOnly!4382',role='APPROVAL')
        self.client.force_login(another)
        self.assertEqual(self.client.post(url,{'decision':'APPROVED','decision_token':token}).status_code,200)
        self.assertFalse(ApprovalHistory.objects.exists())

    def test_expired_approval_form_is_rejected(self):
        self.client.force_login(self.users['APPROVAL'])
        url=reverse('approval_workflow_detail',args=[self.submission.pk])
        token=self.token(url)
        import time
        with patch('django.core.signing.time.time',return_value=time.time()+1801):
            self.assertEqual(self.client.post(url,{'decision':'APPROVED','decision_token':token}).status_code,200)
        self.assertFalse(ApprovalHistory.objects.exists())

    def test_atomic_stage_claim_rejects_stale_database_state(self):
        old=TenderSubmission.objects.get(pk=self.submission.pk)
        with transaction.atomic(): advance(TenderSubmission,self.submission,'LEVEL1')
        with self.assertRaises(StaleDecision):
            with transaction.atomic(): advance(TenderSubmission,old,'LEVEL1')
        self.submission.refresh_from_db(); self.assertEqual(self.submission.status,'LEVEL1')

    def test_failure_rolls_back_approval_status_and_history(self):
        self.client.force_login(self.users['APPROVAL'])
        url=reverse('approval_workflow_detail',args=[self.submission.pk]); token=self.token(url)
        from django.db import IntegrityError
        with patch('core.views.ApprovalHistory.objects.create',side_effect=IntegrityError('simulated duplicate')):
            self.assertEqual(self.client.post(url,{'decision':'APPROVED','decision_token':token}).status_code,200)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,'EVALUATED'); self.assertFalse(ApprovalHistory.objects.exists())

    def test_review_cannot_be_reversed_by_replaying_old_form(self):
        self.company.status='PENDING'; self.company.save()
        self.client.force_login(self.users['PROCUREMENT'])
        url=reverse('registration_review_detail',args=[self.company.pk]); token=self.token(url)
        self.client.post(url,{'decision':'APPROVED','decision_token':token})
        self.client.post(url,{'decision':'REJECTED','decision_token':token})
        self.company.refresh_from_db(); self.assertEqual(self.company.status,'APPROVED')

    def test_audit_and_domain_records_cannot_be_edited_through_admin(self):
        self.client.force_login(self.users['ADMIN'])
        log=AuditLog.objects.create(action='Original audit event')
        url=reverse('admin:core_auditlog_change',args=[log.pk])
        self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(self.client.post(url,{'action':'Tampered'}).status_code,403)
        self.assertEqual(self.client.post(reverse('admin:core_auditlog_delete',args=[log.pk]),{'post':'yes'}).status_code,403)
        log.refresh_from_db(); self.assertEqual(log.action,'Original audit event')
        self.assertEqual(self.client.post(reverse('admin:core_tendersubmission_change',args=[self.submission.pk]),{'status':'APPROVED'}).status_code,403)

    def test_role_revocation_removes_django_admin_access(self):
        user=self.users['ADMIN']; self.client.force_login(user)
        User.objects.filter(pk=user.pk).update(role='COMPANY')
        self.assertEqual(self.client.get(reverse('admin:index')).status_code,302)

    def test_audit_uses_connection_ip_not_spoofed_proxy_header(self):
        self.client.post(reverse('login'),{'username':'company','password':'wrong'},HTTP_X_FORWARDED_FOR='invalid, 192.0.2.2')
        self.assertEqual(AuditLog.objects.filter(action='Failed login').latest('pk').ip_address,'127.0.0.1')

    @override_settings(DEBUG=False)
    def test_demo_passwords_are_disabled_in_production(self):
        user=self.users['ADMIN']; user.set_password('DemoPass!234'); user.save()
        self.assertFalse(self.client.login(username='admin',password='DemoPass!234'))


class ConcurrentApprovalTests(TransactionTestCase):
    file=SecurityHardeningTests.file

    def setUp(self):
        SecurityHardeningTests.setUpTestData.__func__(type(self))
        SecurityHardeningTests.setUp(self)

    def test_simultaneous_same_stage_approvals_commit_only_one_decision(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        second=User.objects.create_user(username='secondapprover',email='second@example.test',password='Another!8324',role='APPROVAL')
        clients=[Client(),Client()]
        url=reverse('approval_workflow_detail',args=[self.submission.pk])
        payloads=[]
        for client,user in zip(clients,[self.users['APPROVAL'],second]):
            client.force_login(user)
            token=client.get(url).context['form'].initial['decision_token']
            payloads.append({'decision':'APPROVED','comment':'Concurrent review','decision_token':token})
        barrier=Barrier(2)
        def synchronised_advance(*args,**kwargs):
            barrier.wait(timeout=10)
            return advance(*args,**kwargs)
        def post(index):
            close_old_connections()
            try:
                response=clients[index].post(url,payloads[index])
                return (response.status_code,response.content.decode()[:300] if response.status_code>=400 else '')
            finally: close_old_connections()
        with patch('core.views.advance',side_effect=synchronised_advance), ThreadPoolExecutor(max_workers=2) as executor:
            responses=list(executor.map(post,[0,1]))
        self.assertEqual(sorted(code for code,body in responses),[200,302],responses)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status,'LEVEL1')
        self.assertEqual(ApprovalHistory.objects.filter(submission=self.submission).count(),1)

