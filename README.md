# GBU No Dues Management Backend

Production-grade backend service for managing student no-dues workflows, approvals, certificates, verification, and operational monitoring.

## 1. What This Service Does

This API powers the full no-dues lifecycle:

- Student registration and login
- Student profile management
- No-dues application creation and resubmission
- Multi-stage approval workflow (School Office, HOD, Dean, Departments, Accounts)
- Certificate generation and public verification
- Admin management (schools, departments, programmes, users, search, analytics)
- Audit logs, system logs, health and Redis metrics

## 2. Tech Stack

- FastAPI (async API framework)
- SQLModel + SQLAlchemy AsyncSession (ORM and database access)
- PostgreSQL (primary data store)
- Redis (rate limiting and traffic counters)
- Cloudflare Turnstile (bot protection on auth endpoints)
- SMTP (email notifications)
- Pytest + httpx (tests)

## 3. Repository Structure

- app/main.py: app initialization, middleware, router inclusion
- app/api/endpoints: all route handlers
- app/services: business logic, email, PDF, auth, approvals
- app/models: SQLModel entities
- app/schemas: request and response contracts
- app/core: configuration, security, database, RBAC, storage
- tests: async test suite

## 4. Runtime and Environment

### Required environment variables

- DATABASE_URL
- SECRET_KEY
- TURNSTILE_SECRET_KEY (required in production mode)

### Important optional variables

- ENV (development or production)
- ACCESS_TOKEN_EXPIRE_MINUTES
- REDIS_URL
- FRONTEND_URL
- FRONTEND_REGEX
- SMTP_HOST
- SMTP_PORT
- SMTP_USER
- SMTP_PASSWORD
- EMAILS_FROM_EMAIL
- EMAILS_FROM_NAME
- ADMIN_EMAIL
- ADMIN_PASSWORD
- ADMIN_NAME
- DB_SSL_VERIFY
- SUPABASE_URL
- SUPABASE_KEY

### Notes

- In production mode, TURNSTILE_SECRET_KEY cannot be dummy/missing.
- REDIS_URL defaults to local Redis if not overridden.
- Request ID is added in response header: X-Request-ID.

## 5. Local Development

### Start

1. Create and activate virtual environment
2. Install dependencies
3. Set .env values
4. Run server

Example:

```bash
python -m venv gbu_no_dues
# Windows
.\gbu_no_dues\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --reload
```

### Tests

```bash
python -m pytest -q
```

## 6. Security and Access Model

### Authentication

- JWT Bearer auth for protected routes
- Admin login: POST /api/admin/login
- Student login: POST /api/students/login

### Bot protection

Turnstile token is required on:

- POST /api/admin/login
- POST /api/students/register
- POST /api/students/login
- POST /api/verification/forgot-password

### Role model

- admin
- student
- staff
- dean
- hod
- legacy verifier roles (library, hostel, lab, sports, crc, account)

## 7. API Conventions

### Base URL

- Local: http://localhost:8000

### Content type

- JSON for request/response except upload and file responses

### Common success envelope pattern

Many endpoints return direct objects. Some return structured payloads, for example application status endpoints:

```json
{
  "application": { "id": "...", "status": "in_progress" },
  "student": { "full_name": "..." },
  "stages": [],
  "flags": { "is_completed": false }
}
```

### Error shape

```json
{
  "detail": "Human-readable error message"
}
```

## 8. Endpoint Catalog

This section lists all mounted API endpoints from app/main.py.

## 8.1 System

| Method | Path         | Auth | Purpose             |
| ------ | ------------ | ---- | ------------------- |
| GET    | /            | No   | Service health root |
| GET    | /favicon.ico | No   | Favicon response    |

## 8.2 Admin Auth and Management (/api/admin)

| Method | Path                                    | Auth           | Purpose                           |
| ------ | --------------------------------------- | -------------- | --------------------------------- |
| POST   | /api/admin/login                        | No + Turnstile | Admin/staff login                 |
| POST   | /api/admin/register-user                | Admin          | Create user account               |
| GET    | /api/admin/me                           | Bearer         | Current user profile              |
| GET    | /api/admin/users                        | Admin          | List users                        |
| DELETE | /api/admin/users/{user_id}              | Admin          | Delete user                       |
| GET    | /api/admin/students/{input_id}          | Admin          | Get student by id/roll/enrollment |
| GET    | /api/admin/search                       | Admin          | Global search                     |
| GET    | /api/admin/analytics/performance        | Admin          | Performance analytics             |
| GET    | /api/admin/reports/export-cleared       | Admin          | Export cleared records            |
| POST   | /api/admin/schools                      | Admin          | Create school                     |
| GET    | /api/admin/schools                      | Admin          | List schools                      |
| DELETE | /api/admin/schools/{identifier}         | Admin          | Delete school                     |
| POST   | /api/admin/departments                  | Admin          | Create department                 |
| GET    | /api/admin/departments                  | Admin          | List departments                  |
| DELETE | /api/admin/departments/{identifier}     | Admin          | Delete department                 |
| POST   | /api/admin/programmes                   | Admin          | Create programme                  |
| GET    | /api/admin/programmes                   | Admin          | List programmes                   |
| DELETE | /api/admin/programmes/{identifier}      | Admin          | Delete programme                  |
| POST   | /api/admin/specializations              | Admin          | Create specialization             |
| GET    | /api/admin/specializations              | Admin          | List specializations              |
| DELETE | /api/admin/specializations/{identifier} | Admin          | Delete specialization             |
| GET    | /api/admin/system-logs                  | Admin          | System/security logs              |
| GET    | /api/admin/audit-logs                   | Admin          | Business audit logs               |

## 8.3 Student Auth and Profile

| Method | Path                   | Auth           | Purpose                           |
| ------ | ---------------------- | -------------- | --------------------------------- |
| POST   | /api/students/register | No + Turnstile | Register student and return token |
| POST   | /api/students/login    | No + Turnstile | Student login                     |
| GET    | /api/students/me       | Student/Admin  | Get linked student profile        |
| PATCH  | /api/students/update   | Student        | Update own student profile        |

## 8.4 Account

| Method | Path                         | Auth   | Purpose                      |
| ------ | ---------------------------- | ------ | ---------------------------- |
| POST   | /api/account/change-password | Bearer | Change current user password |

## 8.5 Applications (/api/applications)

| Method | Path                                              | Auth                   | Purpose                       |
| ------ | ------------------------------------------------- | ---------------------- | ----------------------------- |
| GET    | /api/applications/pending                         | Verifier/Admin         | Pending tasks for reviewer    |
| POST   | /api/applications/create                          | Student                | Create application            |
| GET    | /api/applications/my                              | Student                | Get own latest application    |
| GET    | /api/applications/status                          | Student/Admin          | Search and view status        |
| GET    | /api/applications/{application_id}/certificate    | Student/Admin          | Download certificate          |
| GET    | /api/applications/{application_id}/proof-document | Student/Admin/Verifier | Download proof doc            |
| PATCH  | /api/applications/{application_id}/resubmit       | Student                | Resubmit rejected application |

## 8.6 Approvals (/api/approvals)

| Method | Path                                     | Auth                   | Purpose                        |
| ------ | ---------------------------------------- | ---------------------- | ------------------------------ |
| GET    | /api/approvals/all                       | Admin/Student/Verifier | List applications with filters |
| GET    | /api/approvals/pending                   | Admin/Student/Verifier | List pending items             |
| GET    | /api/approvals/history                   | Admin/Student/Verifier | Approval history               |
| GET    | /api/approvals/{application_id}/stages   | Admin/Student/Verifier | Stage details                  |
| GET    | /api/approvals/enriched/{application_id} | Admin/Verifier         | Enriched application view      |
| POST   | /api/approvals/{stage_id}/approve        | Verifier/Admin         | Approve stage                  |
| POST   | /api/approvals/{stage_id}/reject         | Verifier/Admin         | Reject stage                   |
| POST   | /api/approvals/admin/override-stage      | Admin                  | Force stage override           |

## 8.7 Common Metadata (/api/common)

| Method | Path                        | Auth           | Purpose                      |
| ------ | --------------------------- | -------------- | ---------------------------- |
| GET    | /api/common/schools         | Public         | School dropdown data         |
| PATCH  | /api/common/{school_code}   | Admin intended | Update school flags          |
| GET    | /api/common/departments     | Public         | Department dropdown data     |
| GET    | /api/common/programmes      | Public         | Programme dropdown data      |
| GET    | /api/common/specializations | Public         | Specialization dropdown data |

## 8.8 Users Convenience (/api/users)

| Method | Path                 | Auth  | Purpose     |
| ------ | -------------------- | ----- | ----------- |
| GET    | /api/users/          | Admin | List users  |
| DELETE | /api/users/{user_id} | Admin | Delete user |

## 8.9 File Utilities

| Method | Path                    | Auth   | Purpose               |
| ------ | ----------------------- | ------ | --------------------- |
| POST   | /api/utils/upload-proof | Bearer | Upload proof document |

## 8.10 Verification and Password Reset

| Method | Path                                      | Auth               | Purpose            |
| ------ | ----------------------------------------- | ------------------ | ------------------ |
| GET    | /api/verification/verify/{certificate_id} | Public             | Verify certificate |
| POST   | /api/verification/forgot-password         | Public + Turnstile | Send OTP           |
| POST   | /api/verification/verify-reset-otp        | Public             | Validate OTP       |
| POST   | /api/verification/reset-password          | Public             | Reset password     |

## 8.11 Jobs and Metrics

| Method | Path                                  | Auth                   | Purpose                     |
| ------ | ------------------------------------- | ---------------------- | --------------------------- |
| POST   | /api/jobs/trigger-stale-notifications | Secret key query param | Trigger reminder job        |
| GET    | /api/metrics/health                   | Public                 | Service health detail       |
| GET    | /api/metrics/dashboard-stats          | Admin                  | Dashboard counters          |
| GET    | /api/metrics/redis-stats              | Admin                  | Redis diagnostics           |
| GET    | /api/metrics/traffic-stats            | Admin                  | Route hit stats             |
| POST   | /api/metrics/clear-cache              | Admin                  | Clear limiter/traffic cache |

## 8.12 Note on Academic Endpoints

The file app/api/endpoints/academic.py defines routes under /api/academic, but this router is not currently included in app/main.py, so those routes are not active in runtime unless explicitly mounted.

## 9. Request and Response Examples

## 9.1 Admin Login

Request:

```json
{
  "email": "admin@gbu.ac.in",
  "password": "StrongPassword123",
  "turnstile_token": "token-from-widget"
}
```

Success response:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "expires_in": 3600,
  "user_name": "Admin",
  "user_role": "admin",
  "user_id": "9f9f..."
}
```

## 9.2 Student Register

Request:

```json
{
  "enrollment_number": "2201012345",
  "roll_number": "2201012345",
  "full_name": "Student Name",
  "mobile_number": "9876543210",
  "email": "student@gbu.ac.in",
  "school_code": "SOICT",
  "password": "Password123",
  "confirm_password": "Password123",
  "turnstile_token": "token-from-widget"
}
```

Success response:

```json
{
  "access_token": "jwt-token",
  "token_type": "bearer",
  "user_id": "...",
  "student_id": "...",
  "student": {
    "full_name": "Student Name",
    "school_code": "SOICT"
  }
}
```

## 9.3 Create Application

Request:

```json
{
  "proof_document_url": "uuid/proof.pdf",
  "remarks": "No dues request",
  "father_name": "Father",
  "mother_name": "Mother",
  "gender": "Male",
  "category": "General",
  "dob": "2001-01-01",
  "permanent_address": "Address",
  "domicile": "UP",
  "department_code": "CSE",
  "programme_code": "BTECH",
  "specialization_code": "AI",
  "is_hosteller": false,
  "section": "A",
  "admission_year": 2022,
  "admission_type": "Regular"
}
```

Success response (excerpt):

```json
{
  "id": "...",
  "student_id": "...",
  "status": "pending",
  "current_stage_order": 1
}
```

## 9.4 Error Example

```json
{
  "detail": "Invalid Department Code: XYZ"
}
```

## 10. HTTP Error Codes and Definitions

| Code | Meaning in this project          | Typical causes                                        |
| ---- | -------------------------------- | ----------------------------------------------------- |
| 200  | Request succeeded                | Standard GET/POST success                             |
| 201  | Resource created                 | Register user, create application                     |
| 204  | No content success               | Delete endpoints                                      |
| 400  | Business validation failed       | Invalid code, old password wrong, bad workflow action |
| 401  | Authentication failed            | Invalid token or bad credentials                      |
| 403  | Authenticated but forbidden      | Role not allowed                                      |
| 404  | Resource not found               | Invalid certificate id, missing record                |
| 422  | Request schema validation failed | Missing required fields, bad payload type             |
| 429  | Rate limit exceeded              | Too many requests from same client                    |
| 500  | Internal server error            | Unhandled exception                                   |

## 11. Debugging Guide

## 11.1 Check request identity

- Read response header X-Request-ID.
- Correlate with server logs for the same request path.

## 11.2 Common auth failures

- 401 on login: check credentials and turnstile_token.
- 401 on protected route: verify Bearer token and token expiry.
- 403 on protected route: role mismatch with route guard.

## 11.3 Common validation failures

- 422: inspect required schema fields in app/schemas.
- 400: check domain validations (school_code, department_code, workflow stage ownership).

## 11.4 Rate-limit behavior

- 429 returns: {"detail": "Rate limit exceeded. Please try again later."}
- For tests, rate limiter can be disabled in test fixtures.

## 11.5 Database troubleshooting

- Verify DATABASE_URL is valid and reachable.
- Startup runs DB connection test and seeding.
- Missing linked entities (student_id, user_id relations) will fail writes.

## 11.6 Storage and file access

- Proof and certificate file URLs are signed before returning to clients.
- Check configured storage backend and credentials for broken links.

## 12. Testing and Quality

- Framework: pytest with async tests
- Full command:

```bash
python -m pytest -q
```

- Endpoint tests exist for all endpoint modules under tests/.

## 13. Operational Notes

- Health endpoint: /api/metrics/health
- Logs endpoints for admins: /api/admin/system-logs and /api/admin/audit-logs
- Stale notification cron endpoint uses shared secret in query string.

## 14. Contribution Checklist

Before opening a pull request:

1. Run full tests and ensure green.
2. Validate any schema changes against endpoint handlers.
3. Confirm role guards for newly added routes.
4. Update this README if you add/remove routes or change payloads.
