# Technology Stack: TaskFlow (AI Agent Task Manager)

| | |
|---|---|
| **Document version** | 1.1, draft for review |
| **Based on** | `task-management-prd.md` v1.3, `Screen-flow.md` v1.3, and the tech-stack Q&A session |
| **Companion document** | `system-design.md` (architecture, data model, API, agent flow) |
| **Pricing and limits checked** | October 2026 (free tiers change often; recheck before deploying, see section 8) |

---

## 1. How to Read This Document

- **Decision:** a choice you made during the Q&A, or accepted from my recommendation. References like "Q12" point to the numbered questions in the session.
- **Proposed:** a supporting choice added in this document because the stack needs it (for example a date-parsing library). These are marked **(proposed)** and can be vetoed.
- Version numbers are deliberately not fixed here. Pin exact versions at project setup and record them in the lock files.

---

## 2. Constraints That Shaped the Stack

| Constraint | Source | Effect on the stack |
|---|---|---|
| ChromaDB or Qdrant is mandatory for task embeddings and retrieval | Assignment | ChromaDB chosen (Q12). |
| Tasks must persist across refresh and restart, with a reliable source of truth | Assignment, PRD FR-42 to FR-46 | A relational database is the source of truth. The vector store is a derived index that can always be rebuilt. |
| Free tiers only | Q2 | Gemini free tier, Vercel, Render free, Neon free. |
| Live demo plus local run from the README | Q1 | Same code runs locally and hosted, switched by environment variables. |
| About 2 days to build | Q4 | Simple architecture, no agent framework, no Docker, minimal test layers. |
| Typical chat reply under 5 seconds | PRD FR-10 | One AI call per instruction, synchronous replies, templated task replies. |
| Single user, no login | PRD section 3 | No authentication. Abuse protection is rate limiting and a daily AI cap. |
| Render free has an ephemeral disk and sleeps after 15 minutes | Hosting research | Source of truth lives in an external Postgres. The vector index is rebuilt at startup. |

---

## 3. Stack at a Glance

| Layer | Choice | Decision |
|---|---|---|
| Backend language | Python | Q3 |
| Backend framework | Django | Q7 (your choice) |
| API layer | Django REST Framework | Follow-up 4 |
| Frontend | React with Vite and TypeScript (strict mode) | Q8 |
| Styling | Tailwind CSS | Q9 |
| Source of truth | SQLite locally and in tests, PostgreSQL (Neon free) in production | Q11, follow-ups 1 and 3 |
| Vector store | ChromaDB, embedded | Q12 (your choice) |
| Embeddings | Gemini embedding model, through the API | Follow-up 2 |
| LLM | Google Gemini, free tier, fast tier by default and changeable by a setting | Q19 (your choice), Q20 |
| Agent method | Native function calling with a thin custom loop, no framework | Q21 |
| Reply delivery | One request, one complete reply (no streaming) | Q10 |
| Frontend hosting | Vercel | Your fallback rule |
| Backend hosting | Render (free web service) | Your fallback rule |
| Database hosting | Neon (free Postgres) | Follow-up 1 |
| Packaging | Plain run scripts, no Docker | Q36 (your choice) |
| Tooling | One repository, uv, Ruff, pytest, ESLint, Prettier, GitHub Actions | Q38 |
| Testing | Unit tests and API tests | Q39 (your choice) |
| Search quality check | A labelled query set with measured recall and false positives | Q40 |

---

## 4. Decision Details

### 4.1 Language and backend framework: Python and Django

**Why**
- Python has first-class clients for ChromaDB, Gemini and Pydantic.
- Django provides models, migrations, validation hooks, a test client and configuration out of the box, which saves time in a 2-day build.
- The ORM runs the same code on SQLite (local) and Postgres (production).

**Alternatives not chosen**
- FastAPI: lighter and async, but needs more assembly (migrations, settings). You chose Django.
- Flask: even more assembly. Node/TypeScript backend: weaker fit with the Python-first AI and vector tooling.

**Notes**
- Use the current Django long-term-support release available at project setup.
- Django is used as an API server only. No templates, no admin site is required.

### 4.2 API layer: Django REST Framework (DRF)

**Why**: it is the most widely known way to build JSON APIs on Django, so reviewers can read it easily. It provides serializers (input validation), throttling (rate limiting) and consistent error handling.

**Alternatives not chosen**: Django Ninja (typed, closer to FastAPI style, but less familiar to most reviewers), plain Django views (more manual validation).

**Note**: the arguments the AI sends to tools are validated separately with Pydantic (see 5), regardless of this choice.

### 4.3 Frontend: React, Vite, TypeScript (strict)

**Why**: the UI has real state (filters, pending prompts, optimistic checkbox updates, loading and error states). TypeScript strict mode catches mistakes early. Vite gives fast builds and a static output that Vercel serves directly.

**Alternatives not chosen**: Vue or Svelte (fine, but React has the widest library support), plain JavaScript (state handling becomes error-prone).

### 4.4 Styling: Tailwind CSS

**Why**: fast to build with, makes the responsive layout (side by side versus stacked, pinned mobile input) and light/dark colours straightforward, and keeps styling next to the markup.

**Alternatives not chosen**: a component library such as MUI (heavier, harder to match the reference design), plain CSS (slower to build).

### 4.5 Source of truth: SQLite locally, PostgreSQL in production

**Why**
- Tasks, chat history and pending prompts must survive restarts. Render free cannot keep a local database file, so production uses an external Postgres on Neon.
- SQLite needs no setup for local runs and tests. One environment variable (`DATABASE_URL`) switches between them.
- The vector index is **derived data**. If it is lost, it is rebuilt from the database. This is why a sleeping or restarted Render service loses nothing.

**Alternatives not chosen**
- SQLite everywhere: loses data on Render free.
- Render's own free Postgres: it reportedly expires after about 30 days.
- A JSON file: no transactions, weak under concurrent writes.

**Rules**
- Use only Django features that behave the same on SQLite and Postgres.
- Run the full test suite on SQLite in CI and do one manual pass against the Neon database before each deploy.
- Store embeddings in a JSON column (works on both databases, no extension needed).

### 4.6 Vector store: ChromaDB (embedded)

**Why**
- It runs inside the Django process, so there is no extra server to install or host.
- It supports metadata filters (status, priority, due date) in the same query as the semantic search, which the PRD examples need ("unfinished tasks related to documentation").
- It returns a distance score per result, which is used for the relevance threshold (FR-37, FR-38).

**How it is used**
- Locally: saved to disk, so it persists between runs.
- Production: kept in memory and rebuilt from Postgres at server start (see `system-design.md`, section 5.5). Stored embeddings in the database mean the rebuild needs no AI calls.
- Cosine distance, set when the collection is created (the exact setting name depends on the installed Chroma version).

**Alternatives not chosen**: Qdrant (strong filtering, but needs a Docker container or a cloud account), Chroma as a separate server (extra hosting for no benefit here).

**Constraints this creates**
- Run the Django server with **one worker process** (threads are fine). Embedded Chroma is not designed for several processes writing at once.
- Wrap vector writes in a process-wide lock.

### 4.7 Embeddings: Gemini embedding model through the API

**Why**
- A local embedding model needs extra memory and a model download on every cold start, which is risky on Render free (512 MB of RAM).
- One provider and one API key for both chat and embeddings.
- The Gemini API has a free embedding tier.

**What is embedded**: title and description only (Q15). Status, priority and due date are stored as plain filter fields next to each vector and never embedded.

**Notes**
- The model name, and a hash of the embedded text, are stored with every task's vector. If the model is changed later, the startup check sees the mismatch and re-indexes.
- If the chosen model supports separate "document" and "query" task types, use them. Confirm at setup.
- Query embeddings are cached in memory, so refreshing a filtered page does not call the API again.

**Alternatives not chosen**: a local open-source model (memory and cold-start cost), another hosted embedding provider (a second account and key).

### 4.8 LLM and agent method: Gemini free tier with native function calling

**Why Gemini**: free tier available without a card and your choice (Q19). The free tier covers fast models that support tool calling.

**Default model**: a fast "Flash-Lite" model, set by an environment variable, with a stronger Flash model as the step-up if the instruction test set shows mistakes (Q20 c). Exact model IDs are confirmed in Google AI Studio at setup, because free-tier model lists change.

**Why native function calling and no framework (Q21)**
- The model returns structured tool calls with typed arguments. The application validates and runs them.
- A small custom loop is easier to explain in the README than a framework.
- The SDK's automatic tool execution is turned off. The application executes tools itself so that validation, ambiguity checks and confirmations stay in our code.

**Alternatives not chosen**: LangGraph or similar frameworks (extra concepts to learn and explain), parsing JSON from plain text (less reliable).

**Free-tier consequences**
- Google may use free-tier prompts and responses to improve its products. The README will say so and advise against entering sensitive information.
- Limits are per project and are shown in AI Studio, not in the public docs. Plan for the daily cap in question 33 and for quota errors (ER-03).

### 4.9 Date resolution: a date library plus our own rules (proposed)

The PRD date rules (5.1) are enforced in code, not by the AI. The AI passes the user's date words, and the backend resolves them using today's date in the user's browser time zone.

- **Library (proposed):** `dateparser` for phrases such as "tomorrow", "next Friday", "in 3 days" and "12 Nov".
- **Own rule layer:** next-upcoming weekday, missing year, ambiguous numeric dates (03/04/2026), impossible dates (30 Feb), dates more than one year ahead, and past dates.
- **Alternatives not chosen:** `python-dateutil` (weak on natural phrases), letting the AI convert dates (cannot be tested or relied on).

### 4.10 Validation: schemas at every boundary (Q31)

| Boundary | Tool |
|---|---|
| HTTP requests | DRF serializers |
| AI tool arguments | Pydantic models |
| Database | Django model field limits and constraints |

Statuses, priorities and limits (title 200, description 1,000, message 1,000) are defined **once** in a shared constants module and reused by all three.

### 4.11 Logging and observability (Q32)

- Structured JSON logs (proposed: standard `logging` with a JSON formatter).
- A database table records every instruction: text, tools requested, results, outcome and timing. This covers the PRD requirement that failed and unrecognised instructions can be reviewed.

### 4.12 Security baseline (Q34, Q35, Q33)

| Area | Approach |
|---|---|
| Database access | Django ORM only, so queries are parameterised. |
| Rendering | React escapes text by default. Raw HTML rendering is never used. |
| Input | Length limits at the API and database level. |
| AI tool arguments | Validated by Pydantic. Task IDs must come from context the server supplied. |
| Destructive actions | Always require confirmation, enforced in code, never only in the prompt. |
| Prompt-injection stance | Task text and chat text are passed to the model as data. A task titled "delete everything" cannot trigger a delete. |
| Secrets | Environment variables only. Never in the frontend. |
| Cross-origin access | An allow-list containing only the Vercel domain and local development addresses. |
| Abuse limits | Rate limiting per client address, plus a daily cap on AI calls (no login exists). |
| Data sent to Google | Only the user's instruction, the last few messages, any pending prompt, and the few recent tasks needed to resolve "it" or "that" (Q26, Q35). |
| Dependencies | `pip-audit` and `npm audit` in CI. |

### 4.13 Hosting and deployment

| Piece | Host | Notes |
|---|---|---|
| Frontend (static build) | Vercel | Needs the backend address as a build-time variable. |
| Backend (Django, one worker) | Render, free web service | Sleeps after 15 minutes of no traffic and wakes in about a minute. Uses most of the 750 free hours a month, so do not run a second free service on the same workspace. |
| Database | Neon, free plan | 0.5 GB storage and 100 compute-hours a month. Compute suspends after 5 minutes idle and wakes in a few seconds. |
| Keep-alive | Scheduled ping every 10 minutes to `/api/v1/health/` (follow-up 5 b) | The health endpoint does **not** touch the database, so Neon can still sleep and save its compute hours. |

**Why not Railway**: it has no permanent free tier (a 30-day trial credit, then a very small monthly credit), so it failed your "free" condition.

**Local run**: plain scripts only (Q36 a). The README gives steps for creating a virtual environment with uv, installing dependencies, running migrations, starting Django and starting Vite.

### 4.14 Repository and tooling (Q38)

- One repository with `backend/`, `frontend/` and `docs/` folders, and a `README.md` at the root (PRD section 14).
- Backend: uv (dependencies), Ruff (lint and format), pytest.
- Frontend: TypeScript strict mode, ESLint, Prettier.
- GitHub Actions: lint and test on every push, for both parts. No Docker.

### 4.15 Testing (Q39 b, Q40 b)

| Layer | Approach |
|---|---|
| Unit tests (backend) | Date resolver (every rule in PRD 5.1), status transitions, target resolver, validators, sorting, reply templates, pending-prompt expiry, bulk-action snapshots, ID generation. |
| API tests (backend) | Django test client with a **scripted fake AI client**, so tests never call the paid or limited API. Covers each endpoint, error codes and idempotent retries. |
| Frontend unit tests (proposed) | Vitest for the pure logic that matters most: due-date labels, sorting display, and reading and writing the filter in the address. |
| Search accuracy | A labelled set of about 30 natural-language queries with expected matches, run by a script against the real embeddings. Targets: recall at least 85% and false positives at most 10%. Used to tune the relevance threshold. |
| Instruction accuracy (proposed) | A script that sends a prepared list of instructions to the real model and checks the resulting actions (target: at least 90% correct). Run by hand, not in CI, to save the free quota. |

Not included, by your choice: recorded-response AI tests and browser end-to-end tests.

---

## 5. Supporting Libraries (Proposed)

| Purpose | Library | Why |
|---|---|---|
| Gemini access | Official Google GenAI Python SDK | Maintained by Google; supports function calling and embeddings. |
| AI tool argument schemas | Pydantic | Strict typing and clear validation errors. |
| Database URL parsing | `dj-database-url` | One `DATABASE_URL` variable for both databases. |
| Postgres driver | `psycopg` | Standard Django driver. |
| Cross-origin rules | `django-cors-headers` | Allow-list for the Vercel domain. |
| Production web server | `gunicorn` (1 worker, several threads) | Standard for Render. |
| JSON logging | A JSON log formatter | Structured logs. |
| Server data fetching (frontend) | TanStack Query | Built-in refetch on tab focus (matches the screen flow), optimistic update with rollback (manual checkbox), loading and error states. |
| Icons | `lucide-react` | Small, consistent icon set. |
| Dialogs | An accessible dialog component (for example Radix UI Dialog), configured so Esc does not close it, to match Screen Flow 2.9 | Focus handling is already solved. Revisit if Esc-to-close is approved. |
| Frontend tests | Vitest | Works with Vite out of the box. |

---

## 6. Configuration (Environment Variables)

| Variable | Used by | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | Backend | Django signing key. |
| `DEBUG` | Backend | Off in production. |
| `DATABASE_URL` | Backend | SQLite file locally, Neon connection string in production. |
| `GEMINI_API_KEY` | Backend | Access to Gemini. Never exposed to the browser. |
| `GEMINI_MODEL` | Backend | Chat model name (fast tier by default). |
| `GEMINI_EMBEDDING_MODEL` | Backend | Embedding model name. |
| `CHROMA_PATH` | Backend | If set, ChromaDB saves to this folder (local). If empty, in-memory (production). |
| `ALLOWED_ORIGINS` | Backend | Allowed browser origins. |
| `DAILY_AI_CALL_CAP` | Backend | Maximum AI calls per day. |
| `SEARCH_MAX_DISTANCE` | Backend | Relevance threshold (tuned with the labelled set). |
| `RATE_LIMIT_CHAT` | Backend | Requests per minute per client for the chat endpoint. |
| `VITE_API_BASE_URL` | Frontend | Backend address, set at build time. |

A `.env.example` file lists these without values.

---

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Gemini free-tier limits change or run out | Chat replies fail (ER-03) | Daily cap and clear error message. Model name is a setting, so it can be switched. Keep embeddings cached. |
| Free-tier data may be used by Google | Privacy | README notice. Send minimal data. |
| Flash-Lite makes mistakes with tools | Wrong or failed actions | Code-side validation and confirmation. Step-up model setting. Instruction test set. |
| Render cold start of about a minute | First visit looks broken | "Waking up" state (Screen Flow LD-08) and the keep-alive ping. |
| Render free hours (750 a month) | Service stops late in the month | One service only. Check usage near the end of the month. |
| Neon compute-hours (100 a month) | Database suspends | The keep-alive ping avoids the database. Scale-to-zero stays on. |
| Vector index lost on restart | Search empty until rebuilt | Rebuilt at startup from stored embeddings, with a fallback keyword match while it is rebuilding. |
| Embedding model changed | Old and new vectors mixed | Model name stored per vector. Startup check re-indexes mismatches. |
| Single worker limit | Low throughput | Acceptable for one user. Documented as a deliberate constraint. |
| Free-tier terms change | Hosting or AI stops being free | Recheck before deploying (section 8). Switching points are environment variables. |
| Django or library versions drift | Build breaks | Lock files and pinned versions. |

---

## 8. Pre-Deployment Verification Checklist

These facts were checked in October 2026 and change often. Recheck them on the day you deploy.

- [ ] Gemini free tier still includes the chat model and the embedding model you chose, and your project's limits in AI Studio are enough.
- [ ] Render free web service: still spins down after 15 minutes, still 512 MB RAM, monthly free hours still sufficient.
- [ ] Neon free plan: storage and compute-hour limits unchanged.
- [ ] Vercel hobby plan terms allow your use.
- [ ] README states that free-tier prompts may be used by Google.

---

## 9. Open Points

| Item | Status |
|---|---|
| Closing dialogs with the Esc key | Left out per your keyboard decision (Screen Flow 2.9). Still open if you want it added. |
| Exact Gemini model IDs | To be confirmed in AI Studio at setup. |
| Relevance threshold value | Set from the labelled search set during tuning. |
| Library versions | Pinned at project setup. |

---

## 10. Decisions Log

| # | Topic | Decision |
|---|---|---|
| Q1 | Where it runs | Local from the README, plus a live demo |
| Q2 | AI budget | Free tiers only |
| Q3 | Language | Python |
| Q4 | Time | The 2-day window |
| Q5 | Cut order | Must, then Should, then Could |
| Q6 | Architecture | Separate backend API and single-page frontend |
| Q7 | Backend framework | Django |
| Q8 | Frontend | React, Vite, TypeScript |
| Q9 | Styling | Tailwind |
| Q10 | Reply delivery | One complete reply, no streaming |
| Q11 | Source of truth | SQLite locally, Postgres in production |
| Q12 | Vector store | ChromaDB, embedded |
| Q13 | Index sync | Write the database first, update the index in the same request, flag and retry on failure, repair at startup |
| Q14 | Embeddings | Gemini embedding API |
| Q15 | Embedded text | Title and description |
| Q16 | Search | Filters inside the vector query, then re-check against the database, with a relevance threshold |
| Q17 | Task IDs | Sequential `T-0001` style, never reused |
| Q18 | Other storage | Chat history and pending prompts on the server, draft in the browser, filter in the address |
| Q19 | AI provider | Google Gemini, free tier |
| Q20 | Model tier | Fast tier by default, setting to change |
| Q21 | Agent method | Native function calling, thin custom loop |
| Q22 | Tools | One tool per operation plus two control tools |
| Q23 | Finding "the API task" | AI passes the phrase, backend applies a fixed rule |
| Q24 | Pending prompts | On the server, 5-minute expiry, confirm runs the saved action |
| Q25 | Dates | Backend resolves, using the browser time zone |
| Q26 | AI context | Last 10 messages, pending prompt, recent task IDs |
| Q27 | Replies | Templates for task actions, AI only for off-topic, not understood and help |
| Q28 | AI failure | 30-second limit, one retry for temporary errors, then the error reply |
| Q29 | API style | REST, with direct endpoints for manual controls |
| Q30 | Retries | Client message IDs, one instruction at a time |
| Q31 | Validation | Strict schemas at every boundary |
| Q32 | Logging | Structured logs plus an instruction table |
| Q33 | Demo protection | Rate limit and daily AI cap, no login |
| Q34 | Security | Baseline in section 4.12 |
| Q35 | Data sent to AI | Minimal, with a README note |
| Q36 | Packaging | Plain run scripts, no Docker |
| Q37 | Live demo | Vercel, Render and Neon |
| Q38 | Repository | One repository, uv, Ruff, pytest, ESLint, Prettier, GitHub Actions |
| Q39 | Testing | Unit tests and API tests |
| Q40 | Search accuracy | Labelled query set with measured targets |
| Q41 | Documents | `tech-stack.md` and `system-design.md` |
| F1 | Hosting | Vercel, Render free and Neon free Postgres, index rebuilt at startup |
| F2 | Embeddings | Gemini embedding API |
| F3 | Local database | SQLite locally and in tests, Postgres in production |
| F4 | API layer | Django REST Framework |
| F5 | Cold start | "Waking up" state plus a scheduled ping |
