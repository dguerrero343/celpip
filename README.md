# CELPIP Writing Coach

Foundation for a commercial, multi-user CELPIP training platform. It provides a containerized edge, API, database, migration system, JWT authentication, a writing task catalog, owned submission history, provider-neutral evaluation orchestration, and progress tracking.

## Architecture

The system starts as a **modular monolith**. FastAPI modules own HTTP concerns, services own use cases, SQLAlchemy models own persistence mappings, and Pydantic schemas define API contracts. This keeps transactions and deployments simple while preserving seams that can later become independent services.

```text
Browser -> Nginx -> Next.js
                 -> FastAPI -> service layer -> PostgreSQL
                                      |
                                      +-> OpenAI Responses API adapter
```

- **API first:** version-ready routes and OpenAPI contracts; the frontend has no database access.
- **Database first:** PostgreSQL stores full history. UUID keys, foreign keys, uniqueness constraints, and query-oriented indexes support multiple users safely.
- **Security:** Argon2 password hashing, short-lived signed JWT access tokens, role claims, active-account enforcement, strict configuration, and no secrets in images.
- **AI portability:** `app/ai` owns the provider contract, OpenAI adapter, structured schema, context reduction, token limits, and cost capture. Controllers call an evaluation service, never OpenAI directly.
- **Operations:** Nginx is the public edge; each application is independently containerized and health checked. Alembic owns schema evolution.

### Scale path

Keep the API stateless and add replicas behind the edge. Move evaluations to a PostgreSQL-backed job outbox and worker before traffic makes synchronous calls unreliable. Add Redis only when a measured need appears (rate limits, queues, or caching). Send analytics to read replicas or a warehouse once reporting workloads affect OLTP. Add `tenant_id` to tenant-owned tables before team/organization accounts are introduced; current user-level ownership already enforces the first isolation boundary.

### Known risks and planned controls

| Risk | Phase-one control | Next control |
| --- | --- | --- |
| AI cost/context growth | Conservative preflight budget, compressed context, output cap, cached-token pricing, and usage records | Per-user quotas and asynchronous jobs |
| Model output drift | Strict structured output schema, score validation, and response metadata audit | Versioned evaluation benchmarks |
| JWT revocation | Short expiry and active-user lookup on protected requests | Rotating refresh-token records and revocation |
| Abuse / credential attacks | Strong hashing and non-enumerating login errors | Edge rate limiting, email verification, audit events |
| Reporting pressure | Indexed score and submission histories | Read replica / analytics store |

## Repository layout

```text
frontend/                 Next.js dashboard and demo experience
backend/
  alembic/                versioned database migrations
  app/
    api/                  HTTP routes and dependencies
    auth/                 JWT and password primitives
    database/             engine, sessions, declarative base
    models/               SQLAlchemy persistence models
    schemas/              Pydantic request/response contracts
    services/             application use cases
    ai/                   provider contract, OpenAI adapter, schema, token budget
nginx/                    reverse-proxy configuration
docker-compose.yml        local/VPS-compatible service topology
```

## Run locally

1. Copy `.env.example` to `.env` and replace `POSTGRES_PASSWORD` and `JWT_SECRET_KEY`. Set `DEMO_MODE=true` for the read-only dashboard. Set `OPENAI_API_KEY` to enable new writing evaluations; leave it empty to run the dashboard and all pre-evaluated demo content without OpenAI access.
2. Build and start. The one-shot `migrate` service upgrades the schema before the API starts:

   ```powershell
   docker compose up --build
   ```

3. Open `http://localhost` (or the port selected by `HTTP_PORT`), API documentation at `/api/docs`, and health at `/api/health`.

The migration chain loads four original exercises plus an inactive demo profile with two sample submissions, scores, corrections, and recommended practice. `GET /api/demo/dashboard` is available only when `DEMO_MODE=true`; it never invokes an AI provider. Leave `DEMO_MODE=false` outside local/demo environments.

For a public VPS, terminate TLS before this stack (or add certificate automation to Nginx), set `APP_ENV=production`, and use host-managed secrets rather than a copied `.env` file.

Register and log in with JSON:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost/api/auth/register -ContentType application/json -Body '{"email":"student@example.com","password":"a-strong-password","first_name":"Sam","current_celpip_score":7,"target_celpip_score":10}'
Invoke-RestMethod -Method Post -Uri http://localhost/api/auth/login -ContentType application/json -Body '{"email":"student@example.com","password":"a-strong-password"}'
```

Browser users can create an account at `/register`, sign in at `/login`, and access their protected workspace at `/account`. Browser sessions use an HttpOnly, SameSite cookie; bearer-token authentication remains available for API clients and Swagger. `POST /auth/logout` clears the browser session.

## Writing workflow

All writing routes require the bearer token returned by login. The initial migration chain seeds four original CELPIP-style email and survey prompts.

The authenticated browser workspace mirrors the official CELPIP Writing structure:

- Task 1 — Writing an Email: 27 minutes, 150–200 words.
- Task 2 — Responding to Survey Questions: 26 minutes, 150–200 words.
- Each attempt begins with a non-skippable 59-second introduction. PostgreSQL stores the preparation and writing deadlines, selected mode, autosaved response, and Help Mode interaction summary. The backend enforces deadlines and ownership, so refreshing or modifying browser state cannot reset the timer or change a locked mode. At `00:00`, editing is locked, the last server-saved nonblank response is submitted, and the student is taken to structured feedback.

The browser routes are `/practice/1/intro`, `/practice/1`, and `/practice/1/result` (replace `1` with `2` for Task 2).

### Optional Help Mode

During the 59-second preparation period, a student can choose either **Guided Practice** or **Test Simulation**. The selection is locked when writing begins. Test Simulation preserves the normal prompt, timer, editor, word count, autosave, and submit interface without exposing hints. Guided Practice adds an accessible, collapsible panel containing a task-specific structure, placeholder-based sentence frameworks, a natural vocabulary and phrase bank, a checklist derived from the prompt, and a Level 12 quality checklist. It never provides a complete answer and opening the panel does not pause the timer.

A student can have only one active writing attempt across Task 1 and Task 2. Reopening the same task restores its timer and saved response; starting the other task returns a conflict until the current attempt is submitted or expires. PostgreSQL enforces this rule with a partial unique index as well as service-level validation.

Help content is generated by the backend through the configured OpenAI Responses API using a strict Pydantic JSON schema. It sends the task type, prompt, category, target score, and at most three compact weakness labels—not full writing history. Validated plain-text content is saved once on the shared `writing_tasks` record as JSONB with its model and prompt version, then reused for future attempts. Invalid content is rejected and is never rendered as HTML.

Without `OPENAI_API_KEY`, the same flow uses clearly marked deterministic demo guidance. Starting the app, logging in, opening exercises, autosaving, and viewing saved data do not require OpenAI. Only live generation and evaluation are disabled. No additional environment variable is required for Help Mode.

Apply migrations through `20260802_0008` before using the feature:

```powershell
docker compose run --rm migrate
```

Progress and submission history distinguish **Guided Practice Result** from **Test Simulation Result**; guided work is not penalized or blended into the test-simulation summary.

### Rolling learning profile

Each completed evaluation adds immutable weakness observations instead of replacing the student's history. Stable issue keys record whether a weakness is new, improving, stable, worsened, or no longer present. The deterministic ranking gives Test Simulation evidence a weight of `1.0`, Guided Practice evidence a weight of `0.4`, and applies `0.88` recency decay per evaluated attempt. Frequency totals remain separated by attempt type.

Only the top three persistent weakness labels are sent to the evaluator. The evaluator returns exactly one measurable objective for the next attempt and, when an objective already exists for the same attempt type, assesses it as achieved, partially achieved, or not achieved. Objectives for Guided Practice and Test Simulation are independent. The result screen shows the next objective and the previous objective assessment.

Evaluator instructions are fixed in code and stored with `evaluator_prompt_version=2026-08-02.v2`; the model cannot rewrite its own rules. Administrators can call `GET /api/admin/evaluation-consistency` or review the admin panel to compare count, average score, score spread, and average same-user change by prompt version and attempt type. These are stability indicators, not proof of scoring accuracy, so prompt changes should still be evaluated against a representative labeled fixture set before promotion.

### Question-bank administration

Set `ADMIN_EMAILS` to a JSON list of trusted account emails, then sign out and back in so the account receives an administrator session. Administrators can open `/admin` to create and edit exercises, move drafts through review, approve or retire prompts, inspect assignment inventory, generate optional AI drafts, and review the last 30 days of token and cost totals. AI-generated prompts always enter `DRAFT` status and cannot reach students until an administrator approves them.

Student practice now requests the next approved exercise from the backend. PostgreSQL records a task-family assignment before the introduction begins and prevents that family from ever being assigned to the same student again. When a student exhausts the approved inventory, the API reports that no unseen exercise is available instead of resetting their history.

```text
GET  /api/writing/tasks
GET  /api/writing/tasks/{task_id}
POST /api/writing/submissions
GET  /api/writing/submissions
GET  /api/writing/submissions/{submission_id}
POST /api/writing/submissions/{submission_id}/evaluation
GET  /api/writing/progress
POST /api/writing/attempts
GET  /api/writing/attempts/active
GET  /api/writing/attempts/{attempt_id}
PATCH /api/writing/attempts/{attempt_id}/mode
PATCH /api/writing/attempts/{attempt_id}/autosave
GET  /api/writing/attempts/{attempt_id}/help
POST /api/writing/attempts/{attempt_id}/submit
GET  /api/admin/evaluation-consistency
```

The server calculates word counts and enforces submission ownership. Evaluation is idempotent and persists the structured result, score history, compressed student context, exact API token usage, estimated cost, and current score in one transaction.

When `OPENAI_API_KEY` is set, the injected adapter uses the Responses API with a strict Pydantic output schema. Stable evaluator instructions precede the variable student payload to improve automatic prompt-cache reuse. Student history is normalized, deduplicated, capped, and included only while it fits. A conservative, offline byte-based input bound prevents an over-budget request before it incurs API cost; the essay itself is never silently truncated. `MAX_RESPONSE_TOKENS` caps generation, and the price settings distinguish cached input, uncached input, and output tokens. Keep those rates synchronized with the selected model's current pricing.

The key is read only on the backend. Do not place it in frontend variables or commit it. With no key, new evaluation requests return an explicit `503` while all non-AI routes remain available.

## AI usage and cost report

Authenticated users can open `/usage` to review successful evaluation calls, input and output tokens, model totals, and locally estimated USD cost. The API is available at `GET /api/usage/report` and accepts optional `start_date` and `end_date` query parameters for periods up to 180 days. Students see only their own usage; administrators see organization-wide and per-user totals.

The local estimate uses token counts returned by the Responses API and the three pricing values configured in `.env`. Keep those values aligned with the selected model. For authoritative billing reconciliation, create a separate organization Admin API key and set `OPENAI_ADMIN_KEY`; set `OPENAI_PROJECT_ID` as well so unrelated organization costs are excluded. This credential is used only by the backend to call the OpenAI organization Costs endpoint and is never returned to the browser. Do not reuse or expose it as a frontend variable.

The report intentionally distinguishes local estimates from provider-billed cost. Failed requests are not inserted into `ai_usage`, while provider totals may contain other billable activity from the configured OpenAI project.

## Verification

From `backend/`, install development dependencies and run:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check .
```

The migration can be checked against a real PostgreSQL instance with `alembic upgrade head`, followed by `alembic downgrade base` in a disposable database.

## Phase handoff

- **Infrastructure:** Compose defines frontend, backend, PostgreSQL, and Nginx. Test with `docker compose config` and the health URLs.
- **Database:** all seven requested product tables plus role/account metadata are created by the initial Alembic migration. Test with `alembic upgrade head`.
- **API skeleton:** application lifecycle, configuration, logging, CORS, health, and error-safe startup are in place. Test `/health` and `/docs`.
- **Authentication:** registration, login, `GET /auth/me`, password hashing, duplicate-email handling, and protected-request validation are implemented. Test with `backend/tests/test_auth.py` or the commands above.
- **Writing workflow:** task discovery, submissions, ownership-safe history, OpenAI evaluation persistence, and progress summaries are implemented. Test with `backend/tests/test_writing_workflow.py` and `backend/tests/test_openai_provider.py`.
- **Help Mode:** server-authoritative attempts, cached structured guidance, autosave recovery, mode locking, and split progress are covered by `backend/tests/test_help_mode.py`; the responsive frontend is type-checked in the production Next.js build.
- **Rolling learning profile:** persistent weakness weighting, objective carry-forward, prompt versioning, and attempt-type separation are covered by `backend/tests/test_writing_workflow.py` and `backend/tests/test_openai_provider.py`.

Recommended next step: add per-user evaluation quotas, then move calls behind an idempotent PostgreSQL-backed job worker before scaling API replicas.
