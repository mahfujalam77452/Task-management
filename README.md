# TaskFlow · AI Task Manager

TaskFlow is a single-page task manager designed around a natural-language assistant. Create, search, update, move, complete and delete tasks by typing what you mean, while the board and conversation stay visible together.

## Run locally

Requirements: Node.js 18+ and npm.

```bash
npm install
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). A production build can be checked with:

```bash
npm run build
npm run preview
```

The app runs in local mode when `VITE_API_BASE_URL` is unset. In local mode, tasks and chat are stored in browser LocalStorage. For the persistent backend and Gemini assistant, start Django separately:

```bash
cd backend
python3 -m pip install -r requirements.txt
python3 manage.py migrate
python3 manage.py runserver 0.0.0.0:8000
```

Then start the frontend with `npm run dev`. When `VITE_API_BASE_URL` is empty, the browser automatically uses the backend on the same hostname at port 8000, so both `localhost` and `127.0.0.1` work. Set `GEMINI_API_KEY` in the backend environment to enable Gemini interpretation. Without that key, the backend uses its safe local interpreter; it never exposes the key to the browser.

The backend now supports SQLite or PostgreSQL through `DATABASE_URL`, persisted confirmation prompts, server-authoritative status/delete/sample operations, full PATCH validation for title/description/priority/due date, rate limiting, and ChromaDB/Gemini semantic search when both `GEMINI_API_KEY` and the embedding model are configured. If embeddings are unavailable, a bounded keyword/relevance fallback keeps search usable.

## Using TaskFlow

The board starts empty. Use **Load sample tasks** to add the six reference tasks, or start with a message such as:

- `Create a high-priority task to finish the demo tomorrow`
- `Show all unfinished tasks related to documentation`
- `Move the demo task to In progress`
- `Complete the weekly report`
- `Change the priority of the API task to Low`
- `Delete the README task`

Supported operations include:

- Create tasks with optional `high`, `medium`, `low`, `today`, `tomorrow`, or an ISO date.
- List and search by a natural-language phrase, unfinished status, overdue state, or priority.
- Move tasks between **To do**, **In progress**, and **Done**.
- Change task priority.
- Complete and reopen tasks with the completion circle.
- Delete tasks through chat or the row delete button. Every deletion requires confirmation.
- Clear chat without changing tasks.

Click a task row to see its description, full due date and stable task ID. The help button in the header contains ready-to-use prompts. Search state is reflected in the URL, making filtered board views refresh-safe and shareable.

## Product decisions reflected in the UI

- The three status groups are always ordered To do, In progress, Done.
- Open tasks are sorted by due date, then priority, then creation time. Done tasks are sorted by most recently completed.
- Completed tasks are muted and never marked overdue.
- Empty messages are ignored, messages over 1,000 characters cannot be sent, and destructive actions are never applied without confirmation.
- This assignment build intentionally has no login or multi-user collaboration, matching the PRD.
