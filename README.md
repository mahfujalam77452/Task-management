# TaskFlow

TaskFlow is a single-page, AI-assisted task manager. Type natural-language instructions in the chat and manage a persistent task board without leaving the page.

The application includes:

- A React/Vite task board and chat assistant on the same page
- Django REST API with SQLite by default and PostgreSQL support
- Gemini structured-action interpretation when `GEMINI_API_KEY` is configured
- A deterministic local command interpreter for development and offline fallback
- ChromaDB semantic task search with lexical/relevance fallback
- Persistent tasks, chat history, confirmations, and ambiguity prompts
- Responsive desktop and mobile layouts

## What TaskFlow can do

Use the assistant to:

- Create tasks with a title, optional description, priority, and due date
- List and find tasks with natural-language search
- Filter by status, priority, today, tomorrow, overdue, or missing due date
- Edit titles, descriptions, priorities, and due dates
- Move tasks between **To do**, **In progress**, and **Done**
- Complete and reopen tasks
- Delete one task or select multiple ambiguous matches before confirming
- Preserve tasks and conversation history after refreshes and application restarts

Examples:

```text
Create a high-priority task to finish the demo tomorrow
Add a task Create the API documentation due date 26-10-2026
Show unfinished tasks related to documentation
Show me the tasks which have no due date
Update the status of the review API task to In-progress
Change the priority of the API documentation task to high
Delete the database task
```

Destructive actions require confirmation. If a command could refer to multiple tasks, the assistant asks you to choose before changing anything.

## Requirements

- Git
- Node.js 18 or newer
- npm
- Python 3.11 or newer recommended
- A virtual-environment-capable Python installation
- Gemini API key only if you want Gemini interpretation and embedding search

The backend can run without a Gemini key in local development. In that case, the built-in deterministic interpreter handles supported task commands and ChromaDB semantic embeddings are unavailable.

## Clone the repository

```bash
git clone https://github.com/mahfujalam77452/Task-management taskflow
cd taskflow
```



## Backend setup

Create a virtual environment in the project root and install the backend dependencies:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -r backend/requirements.txt
```

Create `backend/.env` for local backend settings. Do not commit this file:

```dotenv
DJANGO_SECRET_KEY=replace-with-a-long-random-development-secret
DEBUG=true
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.0-flash
GEMINI_EMBEDDING_MODEL=text-embedding-004
DATABASE_URL=
DATABASE_PATH=taskflow.sqlite3
CHROMA_PATH=
SEARCH_MAX_DISTANCE=0.65
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
RATE_LIMIT_API=120/min
```

Notes:

- `DATABASE_URL` takes precedence over `DATABASE_PATH`.
- An empty `DATABASE_URL` uses SQLite at `backend/taskflow.sqlite3`.
- For PostgreSQL, set `DATABASE_URL` to a valid `dj-database-url` connection string, for example `postgresql://user:password@localhost:5432/taskflow`.
- `CHROMA_PATH` may point to a persistent ChromaDB directory. If empty, ChromaDB uses its default client storage behavior.
- Keep API keys and secret keys in environment variables or a deployment secret manager.

Apply migrations:

```bash
./.venv/bin/python backend/manage.py migrate
```

Run the backend from the project root:

```bash
./.venv/bin/python backend/manage.py runserver 0.0.0.0:8000
```

Verify that it is running:

```bash
curl http://127.0.0.1:8000/api/v1/health/
```

Expected response:

```json
{"status":"ok"}
```

## Frontend setup

Open a second terminal at the project root:

```bash
npm install
npm run dev
```

Open the URL printed by Vite, normally:

```text
http://localhost:5173
```

The checked-in `.env.local` uses relative API requests:

```dotenv
VITE_API_BASE_URL=
```

The Vite development server proxies `/api` requests to Django at `http://127.0.0.1:8000`.

To use a separately hosted backend, set the frontend environment variable before starting Vite:

```dotenv
VITE_API_BASE_URL=https://your-backend.example.com
```

To intentionally run the browser-only LocalStorage mode:

```dotenv
VITE_USE_LOCAL=true
```

LocalStorage mode is useful for UI-only testing, but it does not provide server persistence, Gemini actions, ChromaDB search, or server-side confirmation prompts.

## One-command development checklist

From the project root, use two terminals.

Terminal 1:

```bash
./.venv/bin/python backend/manage.py migrate
./.venv/bin/python backend/manage.py runserver 0.0.0.0:8000
```

Terminal 2:

```bash
npm install
npm run dev
```

Then visit `http://localhost:5173`.

## Project structure

```text
task-management/
├── src/
│   ├── App.tsx              # Main board, chat UI, filters, prompts, API calls
│   ├── main.tsx             # React entry point
│   └── styles.css           # Responsive application styling
├── backend/
│   ├── manage.py             # Django command entry point
│   ├── requirements.txt      # Python dependencies
│   ├── .env                 # Local secrets/configuration; ignored by Git
│   ├── taskflow/
│   │   ├── settings.py      # Database, CORS, throttling, environment config
│   │   ├── urls.py          # /api/v1/ URL prefix
│   │   └── wsgi.py          # Production WSGI entry point
│   └── tasks/
│       ├── models.py        # Task, ChatMessage, PendingPrompt
│       ├── serializers.py   # REST response schemas
│       ├── urls.py          # Task and chat routes
│       ├── views.py         # API, command routing, validation, execution
│       ├── ai.py            # Gemini structured-action interpreter
│       ├── search.py        # ChromaDB embeddings and fallback search
│       ├── tests.py         # Backend regression and API tests
│       └── migrations/      # Database schema migrations
├── task-management-prd.md   # Product requirements
├── Screen-flow.md           # UI and interaction flows
├── system-design.md         # Architecture and API design
├── tech-stack.md            # Technology and deployment decisions
├── vite.config.ts           # Frontend build and /api proxy
├── package.json              # Frontend scripts and dependencies
├── render.yaml               # Render backend deployment blueprint
└── vercel.json               # Vercel frontend build configuration
```

## System design

### Request and action flow

```text
User message
    ↓
React chat composer
    ↓
Django POST /api/v1/chat/messages/
    ↓
Gemini structured action
    ├── unavailable in development → local command interpreter
    └── invalid/unsupported → clear error, no mutation
    ↓
Server validation and task resolution
    ├── exact target → execute
    ├── ambiguous target → saved choice prompt
    └── delete/destructive action → saved confirmation prompt
    ↓
Database mutation
    ↓
Templated assistant response + refreshed task board
```

### Persistence

The relational database is the source of truth:

- `Task` stores title, description, status, priority, due date, completion time, and soft-deletion time.
- `ChatMessage` stores the conversation and client message IDs for safe retries.
- `PendingPrompt` stores unresolved task choices and confirmations with expiry.

SQLite is the default local database. PostgreSQL can be selected with `DATABASE_URL`.

### Search

Task search first applies explicit filters such as status, priority, or due date. Natural-language queries are normalized and searched using:

1. Gemini embeddings stored and queried through ChromaDB when configured
2. Lexical matching and bounded relevance scoring as a fallback

The board receives the same filter returned by the assistant, so search results and visible task groups stay synchronized.

### Safety and validation

The model proposes a structured action; application code decides whether it is valid. The backend validates:

- Message length and client message UUIDs
- Title length and non-empty titles
- Description length
- Allowed status and priority values
- Date formats and date existence
- Supported update fields
- Exact and ambiguous task matches

The model never writes directly to the database. Delete operations are confirmation-gated, and ambiguous operations do not run until the user selects a task.

## API reference

All API routes are under `/api/v1/`.

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health/` | Health check |
| `GET` | `/tasks/` | List tasks; supports `q`, `status`, `priority`, and `due` filters |
| `POST` | `/tasks/sample/` | Create the sample task set |
| `POST` | `/tasks/<uuid>/status/` | Set status to `todo`, `in_progress`, or `done` |
| `PATCH` | `/tasks/<uuid>/` | Edit title, description, priority, or due date |
| `DELETE` | `/tasks/<uuid>/` | Soft-delete a task |
| `POST` | `/tasks/bulk/` | Apply validated status/priority changes to selected IDs |
| `POST` | `/tasks/bulk/preview/` | Preview tasks matching a filter |
| `GET` | `/chat/messages/` | Load recent chat history and active prompt |
| `POST` | `/chat/messages/` | Send a chat instruction |
| `DELETE` | `/chat/messages/` | Clear chat history |
| `POST` | `/chat/prompts/<uuid>/answer/` | Confirm or cancel a pending prompt |

Example:

```bash
curl http://127.0.0.1:8000/api/v1/tasks/
```

## Testing and production build

Run backend tests and Django checks:

```bash
./.venv/bin/python backend/manage.py test tasks
./.venv/bin/python backend/manage.py check
```

Build the frontend:

```bash
npm run build
```

Preview the production frontend build locally:

```bash
npm run preview
```

The production frontend is generated in `dist/`.

## Deployment

### Backend on Render

`render.yaml` defines a Django/Gunicorn service. Configure these deployment secrets in Render:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `ALLOWED_ORIGINS` containing the deployed frontend origin

The blueprint runs migrations during the build and starts:

```bash
gunicorn taskflow.wsgi:application --workers 1 --threads 4 --timeout 30
```

### Frontend on Vercel

`vercel.json` configures the Vite output directory. Set:

```dotenv
VITE_API_BASE_URL=https://your-render-backend.example.com
```

Then deploy the repository as a Vercel project.

For production, set `DEBUG=false`, use a strong generated `DJANGO_SECRET_KEY`, configure PostgreSQL, and restrict `ALLOWED_ORIGINS` to trusted frontend domains.

## Troubleshooting

### `Failed to fetch`

1. Confirm Django is running on port `8000`.
2. Check `http://127.0.0.1:8000/api/v1/health/`.
3. Confirm the frontend is using the expected `VITE_API_BASE_URL`.
4. Restart Vite after changing `.env.local`.

### Tasks disappear after refresh

Make sure the Django backend is running and `VITE_USE_LOCAL` is not set to `true`. LocalStorage mode and API mode use different sources of truth.

### Gemini is unavailable

Check `GEMINI_API_KEY` in `backend/.env`. In development, supported commands continue through the local interpreter. In production, the backend fails closed and reports that no task was changed when the AI provider is unavailable.

### Database changes are missing

Run:

```bash
./.venv/bin/python backend/manage.py migrate
```

### Port already in use

Run Django on another port:

```bash
./.venv/bin/python backend/manage.py runserver 0.0.0.0:8001
```

If you change the backend port, update the Vite proxy in `vite.config.ts` or use `VITE_API_BASE_URL`.

## Security notes

- Never commit `backend/.env`, `.env.local`, API keys, database passwords, or Django secrets.
- Rotate any credential that has been exposed.
- Use `DEBUG=false` in production.
- Restrict `ALLOWED_ORIGINS` in production.
- Use PostgreSQL or another durable managed database for deployed data.
- ChromaDB is a derived search index; the relational database remains the source of truth.
