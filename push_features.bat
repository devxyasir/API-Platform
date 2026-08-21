@echo off
setlocal EnableDelayedExpansion

:: ============================================================================
:: GitHub 20-Feature Git Commit and Push Automation
:: Project: API Platform (devxyasir/API-Platform)
:: ============================================================================

title GitHub 20-Feature Granular Publisher
chcp 65001 >nul 2>&1
color 0B

:: Disable interactive Git pagers (prevents "(END)" hangs in batch execution)
set "GIT_PAGER=cat"
set "PAGER=cat"

echo.
echo ===============================================================================
echo            API PLATFORM - 20 GRANULAR FEATURE-BY-FEATURE PUBLISHER            
echo ===============================================================================
echo.

:: Detect current Git branch
for /f "tokens=*" %%i in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%i"
if "%BRANCH%"=="" set "BRANCH=main"

:: Check Git remote
for /f "tokens=*" %%i in ('git remote get-url origin 2^>nul') do set "REMOTE_URL=%%i"
if "%REMOTE_URL%"=="" (
    echo [ERROR] No git remote 'origin' found.
    echo Please run: git remote add origin ^<repository-url^>
    pause
    exit /b 1
)

echo Current Branch : %BRANCH%
echo Remote Origin  : %REMOTE_URL%
echo.
echo This script organizes your entire project into 20 granular, feature-driven
echo commits and pushes each to GitHub to produce an exceptional commit history:
echo.
echo   [01] chore(infra)            : Git configuration, docker-compose, and runner scripts
echo   [02] docs                    : System architecture and admin design documentation
echo   [03] feat(backend-core)      : FastAPI app bootstrap, environment config, utilities
echo   [04] feat(backend-db)        : SQLAlchemy database engine and Alembic migrations
echo   [05] feat(backend-models)    : Core ORM models (users, orgs, projects, api keys)
echo   [06] feat(backend-models)    : Billing, plans, credits, and pricing models
echo   [07] feat(backend-models)    : Chat, memory, provider config, rate limits, governance
echo   [08] feat(backend-schemas)   : Pydantic validation schemas (OpenAI, Anthropic, admin)
echo   [09] feat(backend-auth)      : JWT authentication, security, middleware envelopes
echo   [10] feat(backend-rate-limit): Rate limiters, background workers, analytics service
echo   [11] feat(backend-services)  : User, organization, project, api key, audit services
echo   [12] feat(backend-services)  : Billing, credits, plan limits, subscription services
echo   [13] feat(backend-providers) : LLM provider integration engine, tokenizers, models
echo   [14] feat(backend-api)       : REST API routes (v1 chat, account, and admin endpoints)
echo   [15] test(backend)           : Pytest automated test suite and OpenAPI specification
echo   [16] feat(frontend-core)     : Next.js client portal setup, styling, and UI components
echo   [17] feat(frontend-pages)    : Client dashboard pages (keys, usage, billing, requests)
echo   [18] feat(admin-core)        : Next.js admin portal setup, theme toggle, UI components
echo   [19] feat(admin-management)  : Admin management (users, orgs, plans, credits, invoices)
echo   [20] feat(admin-governance)  : Admin gateway control, rate limits, audit, risk, security
echo.
echo ===============================================================================
echo.
echo Choose execution mode:
echo   [1] Push All 20 Features Automatically (Recommended)
echo   [2] Step-by-Step Interactive Push (Confirm before each commit)
echo   [3] Dry-Run (Preview staged files for all 20 features)
echo   [4] Exit
echo.
set /p "MODE=Enter your choice (1-4) [default=1]: "
if "%MODE%"=="4" (
    echo Exiting.
    exit /b 0
)

if "%MODE%"=="3" (
    echo.
    echo [DRY RUN MODE] Previewing all 20 feature groups...
    goto :run_dry_run
)

if "%MODE%"=="2" (
    set "INTERACTIVE=1"
) else (
    set "INTERACTIVE=0"
)

:: ============================================================================
:: EXECUTE 20 FEATURE COMMITS
:: ============================================================================

echo.
echo Starting 20 feature commits and pushing to origin/%BRANCH%...
echo.

:: ----------------------------------------------------------------------------
:: [01/20] Infrastructure & Runner Scripts
:: ----------------------------------------------------------------------------
call :prepare_group "01/20" "Infrastructure and Startup Scripts"
git add .gitignore docker-compose.yml start.bat start-dev.bat push_features.bat 2>nul
call :commit_and_push "chore(infra): add project configuration, docker-compose, and startup scripts"

:: ----------------------------------------------------------------------------
:: [02/20] Documentation
:: ----------------------------------------------------------------------------
call :prepare_group "02/20" "System Architecture and Design Documentation"
git add README.md admin-design.md CHAT_PRODUCT_STATUS.md 2>nul
call :commit_and_push "docs: add comprehensive system architecture and admin design documentation"

:: ----------------------------------------------------------------------------
:: [03/20] Backend Core Application Setup
:: ----------------------------------------------------------------------------
call :prepare_group "03/20" "Backend Core Setup and Utilities"
git add backend/.dockerignore backend/.env.example backend/Dockerfile backend/docker-entrypoint.sh backend/requirements.txt backend/requirements-optional.txt backend/run.py backend/pytest.ini backend/app/config.py backend/app/logging_config.py backend/app/errors.py backend/app/utils 2>nul
call :commit_and_push "feat(backend-core): setup FastAPI application, environment config, and utilities"

:: ----------------------------------------------------------------------------
:: [04/20] Database Engine & Alembic Migrations
:: ----------------------------------------------------------------------------
call :prepare_group "04/20" "Database Engine and Migrations"
git add backend/alembic.ini backend/alembic backend/app/database.py 2>nul
call :commit_and_push "feat(backend-db): initialize SQLAlchemy database engine and Alembic migrations"

:: ----------------------------------------------------------------------------
:: [05/20] Core Identity ORM Models
:: ----------------------------------------------------------------------------
call :prepare_group "05/20" "Core Identity and Organization ORM Models"
git add backend/app/models/base.py backend/app/models/user.py backend/app/models/organization.py backend/app/models/project.py backend/app/models/api_key.py backend/app/models/user_settings.py backend/app/models/enums.py 2>nul
call :commit_and_push "feat(backend-models): implement core ORM models for users, orgs, projects, and keys"

:: ----------------------------------------------------------------------------
:: [06/20] Billing, Plans & Pricing ORM Models
:: ----------------------------------------------------------------------------
call :prepare_group "06/20" "Billing, Plans and Pricing ORM Models"
git add backend/app/models/plan.py backend/app/models/subscription.py backend/app/models/credit.py backend/app/models/billing.py backend/app/models/pricing.py 2>nul
call :commit_and_push "feat(backend-models): implement billing, plan, credit, and pricing models"

:: ----------------------------------------------------------------------------
:: [07/20] Chat, Governance, Provider Config ORM Models
:: ----------------------------------------------------------------------------
call :prepare_group "07/20" "Chat, Provider Config and Governance ORM Models"
git add backend/app/models/conversation.py backend/app/models/memory.py backend/app/models/model.py backend/app/models/provider_config.py backend/app/models/rate_limit.py backend/app/models/request_log.py backend/app/models/governance.py backend/app/models/audit.py backend/app/models/security.py backend/app/models/usage.py backend/app/models/__init__.py 2>nul
call :commit_and_push "feat(backend-models): implement chat, provider, rate limit, and governance models"

:: ----------------------------------------------------------------------------
:: [08/20] Validation Schemas
:: ----------------------------------------------------------------------------
call :prepare_group "08/20" "Pydantic Validation Schemas"
git add backend/app/schemas 2>nul
call :commit_and_push "feat(backend-schemas): add Pydantic schemas for OpenAI, Anthropic, auth, and admin"

:: ----------------------------------------------------------------------------
:: [09/20] Authentication, Security & Middleware
:: ----------------------------------------------------------------------------
call :prepare_group "09/20" "Authentication, Security and Middleware Envelopes"
git add backend/app/auth backend/app/middleware backend/app/dependencies.py 2>nul
call :commit_and_push "feat(backend-auth): implement JWT auth security, middleware envelopes, and context"

:: ----------------------------------------------------------------------------
:: [10/20] Rate Limiting, Workers & Analytics
:: ----------------------------------------------------------------------------
call :prepare_group "10/20" "Rate Limiting, Workers and Analytics Service"
git add backend/app/rate_limit backend/app/workers backend/app/analytics 2>nul
call :commit_and_push "feat(backend-rate-limit): implement multi-backend rate limiter and background workers"

:: ----------------------------------------------------------------------------
:: [11/20] Identity & Security Services
:: ----------------------------------------------------------------------------
call :prepare_group "11/20" "Identity, Organization, Project and Audit Services"
git add backend/app/services/user_service.py backend/app/services/user_settings_service.py backend/app/services/organization_service.py backend/app/services/project_service.py backend/app/services/api_key_service.py backend/app/services/audit_service.py backend/app/services/security_service.py backend/app/services/risk_service.py backend/app/services/admin_service.py 2>nul
call :commit_and_push "feat(backend-services): implement user, org, project, key, and security services"

:: ----------------------------------------------------------------------------
:: [12/20] Billing, Plans & Quotas Services
:: ----------------------------------------------------------------------------
call :prepare_group "12/20" "Billing, Plans, Credits and Quota Services"
git add backend/app/services/billing_service.py backend/app/services/credit_service.py backend/app/services/plan_service.py backend/app/services/pricing_service.py backend/app/services/quota_service.py backend/app/services/subscription_service.py backend/app/services/limit_service.py backend/app/services/limits_resolver.py backend/app/services/usage_service.py 2>nul
call :commit_and_push "feat(backend-services): implement billing, plan, quota, and credit services"

:: ----------------------------------------------------------------------------
:: [13/20] AI Models & Multi-Provider Adapters
:: ----------------------------------------------------------------------------
call :prepare_group "13/20" "AI Model Engine and Multi-Provider Adapters"
git add backend/app/services/chat_service.py backend/app/services/conversation_service.py backend/app/services/embedding_service.py backend/app/services/model_service.py backend/app/services/request_logger.py backend/app/services/tokenizer.py backend/app/services/__init__.py backend/app/providers 2>nul
call :commit_and_push "feat(backend-providers): implement AI model services, tokenizers, and provider adapters"

:: ----------------------------------------------------------------------------
:: [14/20] Backend API Endpoints & Main Router
:: ----------------------------------------------------------------------------
call :prepare_group "14/20" "Backend API Endpoints and Routing"
git add backend/app/api backend/app/dependencies.py backend/app/bootstrap.py backend/app/__init__.py backend/app/main.py 2>nul
call :commit_and_push "feat(backend-api): implement API endpoints for v1 chat, account, and admin routes"

:: ----------------------------------------------------------------------------
:: [15/20] Backend Test Suite & OpenAPI Spec
:: ----------------------------------------------------------------------------
call :prepare_group "15/20" "Test Suite and OpenAPI Specification"
git add backend/openapi.json backend/tests 2>nul
call :commit_and_push "test(backend): add Pytest test suite and export OpenAPI specification"

:: ----------------------------------------------------------------------------
:: [16/20] Frontend Client Portal Setup & UI Core
:: ----------------------------------------------------------------------------
call :prepare_group "16/20" "Frontend Client Portal Setup and UI Core"
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/next.config.mjs frontend/next-env.d.ts frontend/Dockerfile frontend/.dockerignore frontend/.env.local.example frontend/.gitignore frontend/public frontend/lib frontend/components frontend/app/layout.tsx frontend/app/globals.css frontend/app/page.tsx frontend/app/login 2>nul
call :commit_and_push "feat(frontend-core): initialize Next.js developer dashboard with Tailwind CSS and UI components"

:: ----------------------------------------------------------------------------
:: [17/20] Frontend Client Dashboard Feature Pages
:: ----------------------------------------------------------------------------
call :prepare_group "17/20" "Frontend Client Dashboard Feature Pages"
git add frontend/app/(dashboard) 2>nul
call :commit_and_push "feat(frontend-pages): build developer dashboard pages for keys, analytics, billing, and logs"

:: ----------------------------------------------------------------------------
:: [18/20] Frontend Admin Portal Setup & UI Core
:: ----------------------------------------------------------------------------
call :prepare_group "18/20" "Frontend Admin Portal Setup and UI Core"
git add frontend-admin/package.json frontend-admin/package-lock.json frontend-admin/tsconfig.json frontend-admin/tailwind.config.ts frontend-admin/postcss.config.mjs frontend-admin/next.config.mjs frontend-admin/next-env.d.ts frontend-admin/Dockerfile frontend-admin/.dockerignore frontend-admin/.env.local.example frontend-admin/public frontend-admin/lib frontend-admin/components frontend-admin/app/layout.tsx frontend-admin/app/globals.css frontend-admin/app/page.tsx frontend-admin/app/login 2>nul
call :commit_and_push "feat(admin-core): initialize Next.js admin portal with theme toggle and UI components"

:: ----------------------------------------------------------------------------
:: [19/20] Frontend Admin Management Pages
:: ----------------------------------------------------------------------------
call :prepare_group "19/20" "Frontend Admin Management Pages"
git add frontend-admin/app/(dashboard)/layout.tsx frontend-admin/app/(dashboard)/overview frontend-admin/app/(dashboard)/users frontend-admin/app/(dashboard)/organizations frontend-admin/app/(dashboard)/projects frontend-admin/app/(dashboard)/plans frontend-admin/app/(dashboard)/subscriptions frontend-admin/app/(dashboard)/credits frontend-admin/app/(dashboard)/invoices 2>nul
call :commit_and_push "feat(admin-management): build admin management pages for users, orgs, plans, and credits"

:: ----------------------------------------------------------------------------
:: [20/20] Frontend Admin Governance & Observability Pages
:: ----------------------------------------------------------------------------
call :prepare_group "20/20" "Frontend Admin Governance and Observability Pages"
git add frontend-admin/app/(dashboard)/models frontend-admin/app/(dashboard)/provider frontend-admin/app/(dashboard)/rate-limits frontend-admin/app/(dashboard)/api-keys frontend-admin/app/(dashboard)/requests frontend-admin/app/(dashboard)/analytics frontend-admin/app/(dashboard)/usage frontend-admin/app/(dashboard)/audit frontend-admin/app/(dashboard)/security frontend-admin/app/(dashboard)/risk frontend-admin/app/(dashboard)/health frontend-admin/app/(dashboard)/settings 2>nul
call :commit_and_push "feat(admin-governance): build admin gateway controls, rate limits, audit, risk, and security pages"

:: ----------------------------------------------------------------------------
:: Final Workspace Sync (Catch-all)
:: ----------------------------------------------------------------------------
call :prepare_group "Final" "Workspace Sync Check"
git add . 2>nul
call :commit_and_push "chore: finalize project setup and workspace sync"

echo.
echo ===============================================================================
echo               ALL 20 FEATURES HAVE BEEN COMMITTED AND PUSHED!                 
echo ===============================================================================
echo.
echo Latest 20 commits:
git --no-pager log --oneline -n 20
echo.
echo View your repository commit history on GitHub:
echo %REMOTE_URL%
echo.
pause
exit /b 0

:: ============================================================================
:: SUBROUTINES
:: ============================================================================

:prepare_group
set "GRP_NUM=%~1"
set "GRP_TITLE=%~2"
echo -------------------------------------------------------------------------------
echo [%GRP_NUM%] Staging %GRP_TITLE%...
echo -------------------------------------------------------------------------------
goto :eof

:commit_and_push
set "COMMIT_MSG=%~1"

:: Check if there are staged changes
git diff --cached --quiet
if errorlevel 1 (
    echo Files to commit:
    git --no-pager diff --cached --name-status
    echo.
    if "%INTERACTIVE%"=="1" (
        set "CONFIRM=y"
        set /p "CONFIRM=Commit and push this feature? [Y/n]: "
        if /i "!CONFIRM!"=="n" (
            echo Skipping this feature. Unstaging...
            git reset >nul 2>&1
            echo.
            goto :eof
        )
    )
    echo Committing: "%COMMIT_MSG%"
    git commit -m "%COMMIT_MSG%"
    if errorlevel 1 (
        echo [ERROR] Commit failed!
        goto :eof
    )
    echo Pushing to origin/%BRANCH%...
    git push origin %BRANCH%
    if errorlevel 1 (
        echo [WARNING] git push returned a warning or error. Continuing to next group...
    ) else (
        echo [SUCCESS] Pushed to origin/%BRANCH%
    )
    echo.
) else (
    echo No changes found to stage for this group. Skipping.
    echo.
)
goto :eof

:run_dry_run
echo.
echo ===============================================================================
echo DRY-RUN PREVIEW FOR ALL 20 FEATURE GROUPS
echo ===============================================================================
echo.

echo [01/20] Infrastructure and Startup Scripts:
git --no-pager status --porcelain .gitignore docker-compose.yml start.bat start-dev.bat push_features.bat

echo.
echo [02/20] System Architecture and Design Documentation:
git --no-pager status --porcelain README.md admin-design.md CHAT_PRODUCT_STATUS.md

echo.
echo [03/20] Backend Core Setup and Utilities:
git --no-pager status --porcelain backend/.dockerignore backend/.env.example backend/Dockerfile backend/docker-entrypoint.sh backend/requirements.txt backend/requirements-optional.txt backend/run.py backend/pytest.ini backend/app/config.py backend/app/logging_config.py backend/app/errors.py backend/app/utils

echo.
echo [04/20] Database Engine and Migrations:
git --no-pager status --porcelain backend/alembic.ini backend/alembic backend/app/database.py

echo.
echo [05/20] Core Identity and Organization ORM Models:
git --no-pager status --porcelain backend/app/models/base.py backend/app/models/user.py backend/app/models/organization.py backend/app/models/project.py backend/app/models/api_key.py backend/app/models/user_settings.py backend/app/models/enums.py

echo.
echo [06/20] Billing, Plans and Pricing ORM Models:
git --no-pager status --porcelain backend/app/models/plan.py backend/app/models/subscription.py backend/app/models/credit.py backend/app/models/billing.py backend/app/models/pricing.py

echo.
echo [07/20] Chat, Provider Config and Governance ORM Models:
git --no-pager status --porcelain backend/app/models/conversation.py backend/app/models/memory.py backend/app/models/model.py backend/app/models/provider_config.py backend/app/models/rate_limit.py backend/app/models/request_log.py backend/app/models/governance.py backend/app/models/audit.py backend/app/models/security.py backend/app/models/usage.py backend/app/models/__init__.py

echo.
echo [08/20] Pydantic Validation Schemas:
git --no-pager status --porcelain backend/app/schemas

echo.
echo [09/20] Authentication, Security and Middleware Envelopes:
git --no-pager status --porcelain backend/app/auth backend/app/middleware backend/app/dependencies.py

echo.
echo [10/20] Rate Limiting, Workers and Analytics Service:
git --no-pager status --porcelain backend/app/rate_limit backend/app/workers backend/app/analytics

echo.
echo [11/20] Identity, Organization, Project and Audit Services:
git --no-pager status --porcelain backend/app/services/user_service.py backend/app/services/user_settings_service.py backend/app/services/organization_service.py backend/app/services/project_service.py backend/app/services/api_key_service.py backend/app/services/audit_service.py backend/app/services/security_service.py backend/app/services/risk_service.py backend/app/services/admin_service.py

echo.
echo [12/20] Billing, Plans, Credits and Quota Services:
git --no-pager status --porcelain backend/app/services/billing_service.py backend/app/services/credit_service.py backend/app/services/plan_service.py backend/app/services/pricing_service.py backend/app/services/quota_service.py backend/app/services/subscription_service.py backend/app/services/limit_service.py backend/app/services/limits_resolver.py backend/app/services/usage_service.py

echo.
echo [13/20] AI Model Engine and Multi-Provider Adapters:
git --no-pager status --porcelain backend/app/services/chat_service.py backend/app/services/conversation_service.py backend/app/services/embedding_service.py backend/app/services/model_service.py backend/app/services/request_logger.py backend/app/services/tokenizer.py backend/app/services/__init__.py backend/app/providers

echo.
echo [14/20] Backend API Endpoints and Routing:
git --no-pager status --porcelain backend/app/api backend/app/bootstrap.py backend/app/__init__.py backend/app/main.py

echo.
echo [15/20] Test Suite and OpenAPI Specification:
git --no-pager status --porcelain backend/openapi.json backend/tests

echo.
echo [16/20] Frontend Client Portal Setup and UI Core:
git --no-pager status --porcelain frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tailwind.config.ts frontend/postcss.config.mjs frontend/next.config.mjs frontend/next-env.d.ts frontend/Dockerfile frontend/.dockerignore frontend/.env.local.example frontend/.gitignore frontend/public frontend/lib frontend/components frontend/app/layout.tsx frontend/app/globals.css frontend/app/page.tsx frontend/app/login

echo.
echo [17/20] Frontend Client Dashboard Feature Pages:
git --no-pager status --porcelain frontend/app/(dashboard)

echo.
echo [18/20] Frontend Admin Portal Setup and UI Core:
git --no-pager status --porcelain frontend-admin/package.json frontend-admin/package-lock.json frontend-admin/tsconfig.json frontend-admin/tailwind.config.ts frontend-admin/postcss.config.mjs frontend-admin/next.config.mjs frontend-admin/next-env.d.ts frontend-admin/Dockerfile frontend-admin/.dockerignore frontend-admin/.env.local.example frontend-admin/public frontend-admin/lib frontend-admin/components frontend-admin/app/layout.tsx frontend-admin/app/globals.css frontend-admin/app/page.tsx frontend-admin/app/login

echo.
echo [19/20] Frontend Admin Management Pages:
git --no-pager status --porcelain frontend-admin/app/(dashboard)/layout.tsx frontend-admin/app/(dashboard)/overview frontend-admin/app/(dashboard)/users frontend-admin/app/(dashboard)/organizations frontend-admin/app/(dashboard)/projects frontend-admin/app/(dashboard)/plans frontend-admin/app/(dashboard)/subscriptions frontend-admin/app/(dashboard)/credits frontend-admin/app/(dashboard)/invoices

echo.
echo [20/20] Frontend Admin Governance and Observability Pages:
git --no-pager status --porcelain frontend-admin/app/(dashboard)/models frontend-admin/app/(dashboard)/provider frontend-admin/app/(dashboard)/rate-limits frontend-admin/app/(dashboard)/api-keys frontend-admin/app/(dashboard)/requests frontend-admin/app/(dashboard)/analytics frontend-admin/app/(dashboard)/usage frontend-admin/app/(dashboard)/audit frontend-admin/app/(dashboard)/security frontend-admin/app/(dashboard)/risk frontend-admin/app/(dashboard)/health frontend-admin/app/(dashboard)/settings

echo.
echo Dry-run preview of 20 feature groups complete.
pause
exit /b 0
