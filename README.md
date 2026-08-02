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
- Each attempt begins with a non-skippable 50-second introduction. The writing deadline is stored in the browser session so a refresh does not reset it. At `00:00`, editing is locked, a nonblank response is submitted automatically, and the student is taken to structured feedback. A blank attempt is locked and shown as unscored without calling the AI provider.

The browser routes are `/practice/1/intro`, `/practice/1`, and `/practice/1/result` (replace `1` with `2` for Task 2). The timer is a practice-interface control, not a server-side exam-proctoring boundary.

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

Recommended next step: add per-user evaluation quotas, then move calls behind an idempotent PostgreSQL-backed job worker before scaling API replicas.
