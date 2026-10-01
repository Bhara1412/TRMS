# Secure Tender Registration & Management System (TRMS)

Implements exactly the 9 SRS functions:
1. Company Registration
2. Authentication
3. Company Profile
4. Tender Submission
5. Registration Review
6. Tender Evaluation
7. Approval Workflow
8. Administration
9. Audit & Notification

## Windows PowerShell setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py seed_demo
python manage.py test
python manage.py runserver
```

Open: http://127.0.0.1:8000/

Demo staff accounts:
- procurement / DemoPass!234
- evaluation / DemoPass!234
- approval / DemoPass!234
- sysadmin / DemoPass!234

Create a Company Representative from the registration screen.

Recommended demo sequence:
1. Register company.
2. Procurement Officer approves it.
3. Company Representative submits tender.
4. Evaluation Officer evaluates it.
5. Approval Committee performs Level 1, Level 2, Final Approval.
6. Show Audit & Notifications.
7. Show Administration.

Security controls include password hashing, password validation, CSRF protection, role checks, ORM queries, upload validation, randomized filenames, audit logging, session timeout, security headers, transaction-protected workflow changes, and enforced sequential approval.

For public deployment, replace the development SECRET_KEY, set DEBUG=False, use HTTPS and secure cookies, configure trusted hosts/origins, use PostgreSQL, and protect document downloads with authenticated storage/views.
