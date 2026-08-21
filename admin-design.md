# Enterprise Admin & Account Management Module

Build a complete **administration, account, organization, subscription, quota, credits, and usage-management system** for the AI API platform.

The goal is to make the administration experience comparable in structure and sophistication to a modern commercial AI API platform such as OpenAI or Anthropic.

This must NOT be a simple CRUD user table.

The system should support:

* users
* organizations
* projects
* account types
* subscription plans
* free/pro/enterprise accounts
* quotas
* token limits
* usage
* credits
* API keys
* rate limits
* model access
* account status
* suspensions
* abuse controls
* billing-ready architecture
* admin permissions
* audit logs
* usage analytics
* manual account adjustments

---

# 1. ADMIN ARCHITECTURE

Create a dedicated administration layer:

```text
/admin
```

The admin system must be completely separated from customer-facing API endpoints.

Architecture:

```text
                    ┌─────────────────────┐
                    │    Admin Dashboard  │
                    │      Next.js        │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Admin API         │
                    │   FastAPI           │
                    └──────────┬──────────┘
                               │
       ┌───────────────────────┼────────────────────────┐
       ▼                       ▼                        ▼
   PostgreSQL                Redis                Audit System
       │                       │                        │
       ▼                       ▼                        ▼
 Users / Plans           Rate limits             Admin actions
 Usage / Credits         Quotas                  Security events
```

---

# 2. ADMIN ROLES

Implement granular administrator roles.

At minimum:

```text
super_admin
admin
support
billing_admin
analyst
moderator
```

Permissions should be granular.

Example:

```text
users.read
users.write
users.suspend
users.delete

plans.read
plans.write

billing.read
billing.write

usage.read

api_keys.read
api_keys.revoke

models.read
models.write

audit.read

system.read
```

A support administrator should NOT automatically have access to billing configuration.

A billing administrator should NOT automatically be able to modify system configuration.

---

# 3. ORGANIZATION MODEL

Do not make the user the only ownership entity.

Use:

```text
User
   │
   ├── Organization
   │       │
   │       ├── Projects
   │       │      ├── API Keys
   │       │      └── Usage
   │       │
   │       └── Members
   │
   └── Personal account
```

Organizations should have:

```text
id
name
slug
owner_id
plan_id
status
created_at
updated_at
```

---

# 4. ORGANIZATION MEMBERS

Support multiple users in one organization.

Membership:

```text
organization_id
user_id
role
status
joined_at
```

Roles:

```text
owner
admin
developer
billing
viewer
```

Example:

```text
Acme Inc.

Owner
 ├── Muhammad
 │     owner
 │
 ├── Sarah
 │     developer
 │
 └── John
       billing
```

---

# 5. ACCOUNT TYPES

Implement account types.

```text
free
pro
team
enterprise
custom
```

Also support internal administrative accounts:

```text
staff
admin
```

Account state and plan must be separate concepts.

For example:

```text
account_type = user
plan = pro
status = active
```

---

# 6. ACCOUNT STATUS

Implement:

```text
active
pending
suspended
restricted
disabled
deleted
```

The admin must be able to change account status.

When suspended:

```text
API requests → rejected
API keys → disabled
new keys → cannot be created
dashboard → accessible with warning
```

When disabled:

```text
API access → completely blocked
dashboard → blocked
```

Do not delete data immediately when an account is disabled.

Use soft deletion.

---

# 7. USER PROFILE

Admin user detail page should show:

```text
User ID
Name
Email
Account type
Plan
Status
Created
Last login
Last API activity
Organization
Projects
API keys
Usage
Credits
Quota
Rate limits
Models
Security events
```

---

# 8. PLAN SYSTEM

Create a flexible plan engine.

Plans:

```text
Free
Pro
Team
Enterprise
Custom
```

Do NOT hard-code plan behavior inside API routes.

Store plan configuration in the database.

Example:

```json
{
  "name": "Pro",
  "slug": "pro",
  "active": true,
  "limits": {
    "requests_per_minute": 300,
    "requests_per_day": 10000,
    "tokens_per_minute": 100000,
    "tokens_per_month": 10000000,
    "concurrent_requests": 20
  }
}
```

---

# 9. PLAN FEATURES

Plans should support feature flags.

Example:

```text
streaming
advanced_models
batch_api
priority_queue
higher_limits
usage_export
team_members
custom_models
webhooks
priority_support
```

Database structure:

```text
plan_features
```

Example:

```text
Pro
 ├── streaming = true
 ├── advanced_models = true
 ├── batch_api = false
 └── priority_queue = true
```

This allows new features without changing the database schema.

---

# 10. PLAN LIMITS

Support limits at multiple levels:

```text
RPM
RPH
RPD

TPM
TPH
TPD
TPM/month

concurrent requests

maximum request size

maximum context size

maximum output tokens
```

The system must calculate the effective limit from:

```text
global limits
+
plan limits
+
organization overrides
+
project overrides
+
API-key overrides
```

The most restrictive applicable rule should normally win unless an explicit admin override exists.

---

# 11. ADMIN PLAN MANAGEMENT

Create:

```text
/admin/plans
```

Admin can:

* create plan
* edit plan
* duplicate plan
* archive plan
* activate/deactivate plan
* configure limits
* configure features
* configure model access

Do not permanently delete plans that have historical subscriptions.

Use:

```text
active
archived
```

instead.

---

# 12. USER PLAN MANAGEMENT

Admin user page should have:

```text
Current Plan: Free
```

with actions:

```text
Change Plan
Upgrade to Pro
Downgrade to Free
Assign Enterprise
Assign Custom Plan
```

Require confirmation before changing a user's plan.

Store plan history:

```text
user_plan_history
```

with:

```text
user_id
old_plan
new_plan
changed_by
reason
created_at
```

---

# 13. TRIAL SYSTEM

Support trials.

Example:

```text
Pro Trial
14 days
```

Store:

```text
trial_started_at
trial_ends_at
trial_plan
trial_status
```

States:

```text
not_started
active
expired
converted
cancelled
```

Admin can:

```text
start trial
extend trial
cancel trial
convert to paid
```

Every manual modification must create an audit event.

---

# 14. CREDITS SYSTEM

Create a proper credit ledger.

Do NOT simply store:

```text
credits = 500
```

without history.

Use a ledger:

```text
credit_transactions
```

Example:

```text
+1000 promotional credits
-25 API usage
+500 admin adjustment
-100 expired credits
```

Each transaction:

```text
id
organization_id
user_id
type
amount
balance_after
reason
reference_id
expires_at
created_at
created_by
```

Types:

```text
grant
usage
refund
adjustment
expiration
purchase
bonus
```

---

# 15. TOKEN ACCOUNTING

Track token usage separately from credits.

For every request:

```text
prompt_tokens
completion_tokens
total_tokens
```

Also:

```text
token_source
```

with:

```text
provider_reported
estimated
```

Never present estimated token counts as provider-confirmed counts.

---

# 16. TOKEN QUOTAS

Support:

```text
daily token quota
weekly token quota
monthly token quota
lifetime quota
```

Example:

```text
Free
10,000 tokens/day

Pro
10,000,000 tokens/month

Enterprise
custom
```

Display:

```text
8,450 / 10,000 tokens used
84.5%
```

---

# 17. TOKEN RESET

Quota periods should be automatic.

Support:

```text
daily
weekly
monthly
billing cycle
```

Do not reset counters by deleting usage records.

Instead use:

```text
period_start
period_end
```

and aggregate usage.

Historical usage must remain available.

---

# 18. USAGE LEDGER

Create an immutable usage record for every completed request.

Example:

```text
usage_records
```

Fields:

```text
id
request_id
organization_id
user_id
project_id
api_key_id
model
provider
prompt_tokens
completion_tokens
total_tokens
credits_used
latency_ms
status
created_at
```

This becomes the source of truth for analytics and billing.

---

# 19. USAGE SUMMARY TABLES

For performance, create aggregation tables.

For example:

```text
usage_daily
usage_hourly
usage_monthly
```

Store:

```text
requests
successful_requests
failed_requests
prompt_tokens
completion_tokens
total_tokens
credits_used
```

Do not calculate every dashboard graph from millions of raw requests.

---

# 20. ADMIN USER SEARCH

The admin must have a powerful user search.

Search by:

```text
email
name
user ID
organization
API key prefix
plan
status
```

Filters:

```text
Free
Pro
Team
Enterprise

Active
Suspended
Disabled

High usage
Low usage
Rate limited
```

---

# 21. USER DETAIL DASHBOARD

Create a detailed user profile page.

Layout:

```text
------------------------------------------------
User
john@example.com

PRO
ACTIVE
------------------------------------------------

Requests       Tokens       Credits
24,532         3.4M        650

------------------------------------------------

Usage Chart
------------------------------------------------

Recent Requests
------------------------------------------------

Projects
------------------------------------------------

API Keys
------------------------------------------------

Plan & Limits
------------------------------------------------

Security Activity
------------------------------------------------
```

---

# 22. ADMIN ACTIONS ON USERS

Provide actions:

```text
Suspend account
Unsuspend account
Disable account
Change plan
Grant credits
Remove credits
Reset quota
Revoke all API keys
Force password reset
Terminate sessions
Change account limits
```

Dangerous actions must require confirmation.

For example:

```text
Suspend user?
This will immediately prevent API requests.
```

---

# 23. MANUAL CREDIT ADJUSTMENT

Admin can grant credits.

Example:

```text
Grant credits

Amount:
50000

Reason:
Customer support compensation
```

Create:

```text
credit_transaction
audit_log
```

Never directly modify the balance without a ledger entry.

---

# 24. MANUAL QUOTA ADJUSTMENT

Allow admin overrides:

```text
User limit
RPM: 500
TPM: 500000
```

Store:

```text
limit_overrides
```

with:

```text
scope
scope_id
metric
value
expires_at
reason
created_by
```

Allow temporary overrides.

Example:

```text
500 RPM
expires in 7 days
```

---

# 25. API KEY ADMIN MANAGEMENT

Admin can view:

```text
key prefix
owner
organization
project
created
last used
status
```

Admin should NOT be able to view the full raw API key.

Actions:

```text
revoke
disable
rotate
```

---

# 26. PROJECT ADMINISTRATION

Admin can inspect:

```text
projects
owner
organization
plan
requests
tokens
API keys
limits
```

Allow project suspension independently of the entire organization.

---

# 27. MODEL ACCESS CONTROL

Allow plans to determine available models.

Example:

```text
Free:
C

Pro:
C
Advanced-C

Enterprise:
C
Advanced-C
Custom
```

Also support organization-specific model permissions.

---

# 28. MODEL LIMITS

Different models can have different limits.

Example:

```text
C
context: 128k
max output: 8k

Advanced-C
context: 200k
max output: 16k
```

Enforce these before forwarding requests upstream.

---

# 29. API REQUEST PRE-FLIGHT

Every incoming request should pass through:

```text
API key validation
       ↓
user status
       ↓
organization status
       ↓
project status
       ↓
plan
       ↓
model permission
       ↓
quota
       ↓
rate limit
       ↓
concurrency
       ↓
provider
```

If any check fails, reject the request before contacting the provider.

---

# 30. EFFECTIVE LIMIT ENGINE

Create a centralized service:

```python
LimitResolver
```

Example:

```python
limits = limit_resolver.resolve(
    user=user,
    organization=organization,
    project=project,
    api_key=api_key,
    model=model
)
```

Return:

```json
{
  "requests_per_minute": 300,
  "tokens_per_minute": 100000,
  "daily_tokens": 1000000,
  "monthly_tokens": 10000000,
  "concurrent_requests": 20
}
```

Do not duplicate limit logic across routes.

---

# 31. BILLING-READY SUBSCRIPTIONS

Create:

```text
subscriptions
```

Fields:

```text
id
organization_id
plan_id
status
provider
external_subscription_id
current_period_start
current_period_end
cancel_at_period_end
created_at
```

Statuses:

```text
trialing
active
past_due
paused
cancelled
expired
```

Do not require Stripe initially.

Create an abstraction:

```python
BillingProvider
```

so Stripe or another billing system can be plugged in later.

---

# 32. INVOICING-READY USAGE

Store enough information for future billing:

```text
model
tokens
requests
unit cost
credits
billing period
```

Never calculate historical billing using today's model price.

Create price snapshots:

```text
usage_records.price_snapshot
```

---

# 33. PRICING SYSTEM

Create model pricing configuration:

```text
model_prices
```

Example:

```text
model = C
input_price = ...
output_price = ...
effective_from = ...
effective_until = ...
```

When usage occurs, record the applicable price version.

This prevents historical billing from changing when pricing changes.

---

# 34. ACCOUNT USAGE PAGE

Users should see:

```text
Current plan
Usage this period
Tokens used
Requests
Credits
Remaining quota
Reset date
```

Example:

```text
Pro

Tokens
3.4M / 10M

Requests
24,532 / unlimited

Credits
650 remaining

Quota resets:
September 1
```

---

# 35. ADMIN OVERVIEW

Create an admin overview dashboard showing:

```text
Total Users
Active Users
New Users
Free Users
Pro Users
Enterprise Users

Requests Today
Tokens Today
Revenue-ready Usage
Credits Consumed

Error Rate
Rate Limit Events
Suspended Accounts
Provider Errors
```

---

# 36. ACCOUNT GROWTH

Charts:

```text
new users
active users
free → pro conversions
plan distribution
requests
tokens
```

Time ranges:

```text
24h
7d
30d
90d
12m
```

---

# 37. PLAN DISTRIBUTION

Display:

```text
Free       72%
Pro        22%
Team        5%
Enterprise  1%
```

Allow clicking a segment to filter users.

---

# 38. HIGH-USAGE DETECTION

Create automatic administrative signals.

Detect:

```text
unusually high token usage
rapid request spikes
repeated rate-limit violations
many API keys
high error rates
suspicious request patterns
```

Do NOT automatically ban users solely based on one metric.

Create:

```text
risk_events
```

that administrators can review.

---

# 39. ABUSE / SECURITY EVENTS

Create:

```text
security_events
```

Types:

```text
failed_login
api_key_abuse
rate_limit_abuse
suspicious_activity
multiple_sessions
credential_rotation
account_lock
```

Admin can mark:

```text
open
investigating
resolved
ignored
```

---

# 40. AUDIT LOGGING

Every administrative modification must be auditable.

Example:

```text
Admin: Sarah
Action: PLAN_CHANGED

User:
john@example.com

From:
Free

To:
Pro

Reason:
Support upgrade

Time:
2026-08-18 20:32
```

Store immutable audit records.

---

# 41. ADMIN ACTIVITY

Create:

```text
/admin/audit
```

Filters:

```text
admin
action
target user
target organization
date
```

Actions:

```text
USER_CREATED
USER_SUSPENDED
USER_UNSUSPENDED
PLAN_CHANGED
CREDITS_GRANTED
CREDITS_REMOVED
QUOTA_RESET
API_KEY_REVOKED
MODEL_ENABLED
MODEL_DISABLED
LIMIT_CHANGED
```

---

# 42. ADMIN DASHBOARD NAVIGATION

Use:

```text
Overview

Users
Organizations
Projects

Plans
Subscriptions
Credits
Usage

API Keys
Models
Rate Limits

Security
Risk Events
Audit Logs

Providers
System Health

Settings
```

---

# 43. USER TABLE DESIGN

Create a dense but readable enterprise table:

```text
┌──────────────────────────────────────────────────────────────┐
│ User             Plan       Usage       Status      Actions │
├──────────────────────────────────────────────────────────────┤
│ john@...         Pro        3.4M        Active       •••    │
│ jane@...         Free       8.2K        Active       •••    │
│ acme@...          Enterprise 42M        Active       •••    │
└──────────────────────────────────────────────────────────────┘
```

Actions should open a contextual menu.

---

# 44. USER DETAIL TABS

Implement:

```text
Overview
Usage
Requests
Projects
API Keys
Plan
Limits
Credits
Security
Activity
```

---

# 45. PLAN DETAIL PAGE

Show:

```text
Plan name
Price
Users
Features
Models
Limits
Token quota
Request quota
```

Include:

```text
Edit plan
Duplicate
Archive
```

---

# 46. CREDIT LEDGER PAGE

Admin can inspect:

```text
User
Transaction
Amount
Balance
Reason
Admin
Date
```

Example:

```text
john@example.com
Grant
+50,000
125,000
Support compensation
Sarah
Aug 18
```

---

# 47. QUOTA RESET

Admin can manually reset a quota.

But instead of deleting usage:

```text
quota_reset_events
```

Record:

```text
user_id
organization_id
period
metric
previous_usage
reset_by
reason
created_at
```

---

# 48. DATA RETENTION

Implement configurable retention.

Examples:

```text
raw requests: 30 days
usage aggregates: 2 years
audit logs: 2 years
billing records: configurable
```

Do not automatically delete financial/audit records simply because request logs expire.

---

# 49. ADMIN SECURITY

Admin dashboard must have stronger security than normal users.

Implement:

```text
admin MFA-ready architecture
session expiration
admin session revocation
login attempt tracking
IP/device metadata where appropriate
role-based access control
```

Sensitive operations should support re-authentication.

---

# 50. ADMIN API ENDPOINTS

Create APIs such as:

```text
GET    /admin/users
GET    /admin/users/{id}
PATCH  /admin/users/{id}

POST   /admin/users/{id}/suspend
POST   /admin/users/{id}/unsuspend
POST   /admin/users/{id}/disable

POST   /admin/users/{id}/credits
POST   /admin/users/{id}/quota-reset

GET    /admin/organizations
GET    /admin/projects

GET    /admin/plans
POST   /admin/plans
PATCH  /admin/plans/{id}

GET    /admin/subscriptions

GET    /admin/usage
GET    /admin/usage/users/{id}

GET    /admin/api-keys
POST   /admin/api-keys/{id}/revoke

GET    /admin/audit-logs
GET    /admin/security-events
```

---

# 51. FRONTEND DESIGN

The dashboard should feel like a serious infrastructure control panel.

Design principles:

* compact navigation
* excellent typography
* strong information hierarchy
* dense tables
* clear status badges
* responsive charts
* keyboard-friendly interactions
* fast filtering
* searchable tables
* pagination
* loading skeletons
* empty states
* confirmation dialogs
* toast notifications

Avoid making every page look like a marketing website.

---

# 52. STATUS SYSTEM

Use consistent statuses.

Examples:

```text
ACTIVE
SUSPENDED
DISABLED
TRIAL
PAST_DUE
EXPIRED
ARCHIVED
```

Use clear visual indicators, but don't rely on color alone.

---

# 53. ADMIN OVERRIDE SAFETY

Every privileged action should require:

```text
permission check
authentication
authorization
validation
audit event
```

High-risk actions should require confirmation.

Examples:

```text
Delete organization
Disable account
Remove credits
Change enterprise limits
Revoke all API keys
```

---

# 54. API RESPONSE FOR QUOTA ERRORS

If quota is exceeded:

```http
429 Too Many Requests
```

Return:

```json
{
  "error": {
    "type": "quota_exceeded",
    "message": "Monthly token quota exceeded.",
    "code": "token_quota_exceeded",
    "request_id": "req_xxx"
  }
}
```

Do not leak internal database details.

---

# 55. API RESPONSE FOR PLAN RESTRICTIONS

If a model is unavailable:

```json
{
  "error": {
    "type": "permission_error",
    "message": "The requested model is not available on your current plan.",
    "code": "model_not_available",
    "request_id": "req_xxx"
  }
}
```

---

# 56. IMPLEMENTATION REQUIREMENT

Create proper service classes:

```text
UserService
OrganizationService
ProjectService

PlanService
SubscriptionService

CreditService
QuotaService
UsageService

ApiKeyService
LimitService

RiskService
AuditService
AdminService
```

Do not put business logic directly inside FastAPI route functions.

---

# 57. DATABASE TABLES

At minimum:

```text
users
organizations
organization_members
projects

plans
plan_features
plan_limits
plan_models

subscriptions
plan_history

api_keys

credit_transactions
usage_records

usage_hourly
usage_daily
usage_monthly

limit_overrides
quota_reset_events

security_events
risk_events
audit_logs

model_prices
```

Use foreign keys, indexes, constraints, and appropriate cascading behavior.

---

# 58. IMPORTANT ACCOUNTING RULE

Credits, usage, quotas, and billing must be separate concepts.

Do NOT treat:

```text
credits
tokens
quota
money
```

as interchangeable.

For example:

```text
Tokens:
3,500,000

Credits:
650

Monthly quota:
10,000,000 tokens

Billing:
$24.73
```

These are different values and should have separate accounting.

---

# 59. IMPORTANT DATA-INTEGRITY RULE

Never silently modify historical usage.

Usage records should be append-only.

If an administrator makes an adjustment:

```text
original record
+
adjustment record
```

rather than modifying historical usage.

This provides a reliable audit trail.

---

# 60. FINAL ADMIN EXPERIENCE

The administrator should be able to open the dashboard and immediately answer:

### Who is using the API?

```text
Users
Organizations
Projects
```

### Who is paying / on which plan?

```text
Free
Pro
Team
Enterprise
```

### How much are they using?

```text
Requests
Tokens
Credits
Estimated cost
```

### Are users hitting limits?

```text
RPM
TPM
Quota
Concurrency
```

### Is the system healthy?

```text
Latency
Errors
Provider availability
Redis
PostgreSQL
```

### Is there suspicious activity?

```text
Risk events
Rate-limit abuse
Security events
```

### Can support help a customer?

Admin should be able to:

```text
inspect account
inspect usage
inspect requests
change plan
grant credits
reset quota
revoke API keys
suspend account
```

while every privileged action is securely permissioned and audited.

---

# 61. ACCEPTANCE CRITERIA

The module is complete only when all of the following work:

### Account

* create user
* login
* create organization
* invite member
* assign role
* suspend user
* restore user

### Plans

* create Free plan
* create Pro plan
* assign plan
* change plan
* plan history

### Usage

* request generates usage
* tokens recorded
* usage appears in dashboard
* daily/monthly aggregates update

### Credits

* grant credits
* consume credits
* refund credits
* adjustment ledger
* balance calculation

### Quotas

* quota enforced
* quota displayed
* quota reset
* admin override

### Rate limits

* RPM enforced
* TPM enforced
* concurrency enforced

### Security

* RBAC
* admin permissions
* audit logging
* API-key revocation
* account suspension

### Dashboard

* overview
* users
* organizations
* plans
* subscriptions
* credits
* usage
* API keys
* models
* rate limits
* security
* audit logs
* system health

### Reliability

* migrations work
* tests pass
* API errors are normalized
* transactions maintain data integrity
* Redis failures are handled appropriately
* PostgreSQL failures are handled appropriately

---

# 62. QUALITY BAR

Do not implement this as a mock dashboard with fake numbers.

Every displayed number should come from the actual database/analytics pipeline.

Do not use hard-coded:

```text
users = 1240
tokens = 5.4M
requests = 83K
```

Use real data.

The dashboard should be fully connected to the FastAPI backend.

The final result should resemble a **real AI API provider's internal control plane**, not a generic admin template.

Prioritize:

```text
correctness
security
data integrity
observability
maintainability
performance
excellent UX
```

over unnecessary visual effects.
