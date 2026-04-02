
```
gbu-no-dues-management-backend
├─ .dockerignore
├─ app
│  ├─ api
│  │  ├─ deps.py
│  │  ├─ endpoints
│  │  │  ├─ academic.py
│  │  │  ├─ account.py
│  │  │  ├─ applications.py
│  │  │  ├─ approvals.py
│  │  │  ├─ auth.py
│  │  │  ├─ auth_student.py
│  │  │  ├─ common.py
│  │  │  ├─ jobs.py
│  │  │  ├─ logs.py
│  │  │  ├─ metrics.py
│  │  │  ├─ students.py
│  │  │  ├─ users.py
│  │  │  ├─ utils.py
│  │  │  ├─ verification.py
│  │  │  └─ __init__.py
│  │  └─ __init__.py
│  ├─ core
│  │  ├─ config.py
│  │  ├─ constants.py
│  │  ├─ database.py
│  │  ├─ department_roles.py
│  │  ├─ rate_limiter.py
│  │  ├─ rbac.py
│  │  ├─ security.py
│  │  ├─ seeding_logic.py
│  │  ├─ storage.py
│  │  └─ __init__.py
│  ├─ main.py
│  ├─ models
│  │  ├─ academic.py
│  │  ├─ application.py
│  │  ├─ application_stage.py
│  │  ├─ audit.py
│  │  ├─ certificate.py
│  │  ├─ department.py
│  │  ├─ enums.py
│  │  ├─ school.py
│  │  ├─ student.py
│  │  ├─ system_audit.py
│  │  ├─ user.py
│  │  └─ __init__.py
│  ├─ schemas
│  │  ├─ academic.py
│  │  ├─ application.py
│  │  ├─ approval.py
│  │  ├─ approval_summary.py
│  │  ├─ audit.py
│  │  ├─ auth.py
│  │  ├─ auth_student.py
│  │  ├─ student.py
│  │  ├─ user.py
│  │  └─ __init__.py
│  ├─ services
│  │  ├─ application_service.py
│  │  ├─ approval_service.py
│  │  ├─ audit_service.py
│  │  ├─ auth_service.py
│  │  ├─ department_service.py
│  │  ├─ email_service.py
│  │  ├─ pdf_service.py
│  │  ├─ student_service.py
│  │  ├─ turnstile.py
│  │  └─ __init__.py
│  ├─ static
│  │  ├─ favicon.ico
│  │  ├─ fonts
│  │  │  ├─ ARIAL.TTF
│  │  │  └─ DejaVuSans-Bold.ttf
│  │  ├─ images
│  │  │  └─ gbu_logo.png
│  │  └─ status.html
│  ├─ templates
│  │  ├─ email
│  │  │  ├─ application_approved.html
│  │  │  ├─ application_created.html
│  │  │  ├─ application_rejected.html
│  │  │  ├─ password_reset.html
│  │  │  ├─ pending_reminder.html
│  │  │  └─ student_welcome.html
│  │  ├─ pdf
│  │  │  └─ certificate_template.html
│  │  └─ verification.html
│  └─ __init__.py
├─ docker-compose.yml
├─ Dockerfile
├─ LICENSE
├─ pytest.ini
├─ README.md
├─ requirements.txt
└─ tests
   ├─ conftest.py
   ├─ test_account.py
   ├─ test_applications.py
   ├─ test_approvals.py
   ├─ test_approvals_workflow.py
   ├─ test_auth.py
   ├─ test_auth_student.py
   ├─ test_departments.py
   ├─ test_email_mock.py
   ├─ test_students.py
   ├─ test_student_registration.py
   ├─ test_users.py
   ├─ test_utils.py
   ├─ test_verification.py
   └─ __init__.py

```