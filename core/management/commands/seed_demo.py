from datetime import date,timedelta
from django.core.management.base import BaseCommand
from core.models import User,TenderCategory,Tender
class Command(BaseCommand):
    help="Create demo users and a sample tender."
    def handle(self,*args,**options):
        password="DemoPass!234"
        data=[
            ("procurement","procurement@trms.local",User.Role.PROCUREMENT),
            ("evaluation","evaluation@trms.local",User.Role.EVALUATION),
            ("approval","approval@trms.local",User.Role.APPROVAL),
            ("sysadmin","sysadmin@trms.local",User.Role.ADMIN),
        ]
        for username,email,role in data:
            u,created=User.objects.get_or_create(username=username,defaults={"email":email,"role":role})
            if created:
                u.set_password(password); u.save()
        admin=User.objects.get(username="sysadmin"); admin.is_staff=True; admin.is_superuser=True; admin.save()
        cat,_=TenderCategory.objects.get_or_create(name="ICT Services")
        Tender.objects.get_or_create(reference_no="TRMS-ICT-001",defaults={
            "title":"Secure ICT Services Tender","category":cat,
            "description":"Demo tender for the TRMS assignment.",
            "closing_date":date.today()+timedelta(days=30),"is_open":True})
        self.stdout.write(self.style.SUCCESS("Demo data ready. Password for demo staff accounts: DemoPass!234"))
