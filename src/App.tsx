import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Check, ChevronDown, ChevronUp, CircleHelp, Clock3, FileText, ListFilter,
  MessageCircle, Plus, RotateCcw, Send, Sparkles, Trash2, X, Zap,
} from "lucide-react";

type Status = "todo" | "progress" | "done";
type Priority = "low" | "medium" | "high";
type Task = {
  id: string; title: string; description: string; status: Status; priority: Priority;
  due?: string; createdAt: string; completedAt?: string;
};
type ChatMessage = { id: string; role: "user" | "assistant"; text: string; kind?: "success" | "question" | "error" };
type PendingPrompt = { id: string; question: string; kind: "confirmation" | "choice"; action?: { task_ids?: string[] } };
type Filter = { q?: string; status?: string; priority?: Priority; due?: string };

const sampleTitles = [
  ["Finish AI presentation", "Prepare the final slides and rehearse the demo.", "high", "progress"],
  ["Review pull request #82", "Check the API changes and leave feedback.", "medium", "todo"],
  ["Send weekly report", "Summarize this week's progress for the team.", "high", "todo"],
  ["Update API documentation", "Document the new authentication endpoints.", "low", "todo"],
  ["Set up database", "Create the initial schema for the project.", "medium", "done"],
  ["Write project README", "Add setup steps and usage examples.", "low", "done"],
] as const;
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const USE_API = import.meta.env.VITE_USE_LOCAL !== "true";
const apiUrl = (path: string) => `${API_BASE}${path}`;
const fromApiTask = (task: Task & { status: string }) => ({
  ...task,
  status: (task.status as string) === "in_progress" ? "progress" as Status : task.status as Status,
});
const toApiStatus = (status: Status) => status === "progress" ? "in_progress" : status;

const statusLabel: Record<Status, string> = { todo: "To do", progress: "In progress", done: "Done" };
const priorityRank: Record<Priority, number> = { high: 0, medium: 1, low: 2 };
const today = () => new Date().toISOString().slice(0, 10);
const id = () => `T-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 5).toUpperCase()}`;
const dateLabel = (value?: string, status?: Status) => {
  if (!value) return status === "done" ? "Completed" : "No due date";
  const date = new Date(`${value}T12:00:00`);
  const now = new Date(`${today()}T12:00:00`);
  const days = Math.round((date.getTime() - now.getTime()) / 86400000);
  if (status !== "done" && days < 0) return `Overdue · ${Math.abs(days)} day${Math.abs(days) === 1 ? "" : "s"}`;
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days > 1 && days < 7) return date.toLocaleDateString("en-US", { weekday: "long" });
  if (days >= 7 && days < 14) return "Next week";
  return date.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" });
};
const fullDate = (value?: string) => value ? new Date(`${value}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short", year: "numeric" }) : "No due date";
const escapeTitle = (text: string) => text.replace(/^(create|add|make|new)\s+(a\s+)?(task\s+)?/i, "").replace(/^["']|["']$/g, "").trim();

function parseFilter(): Filter {
  const p = new URLSearchParams(location.search);
  const f: Filter = {};
  if (p.get("q")) f.q = p.get("q")!;
  if (p.get("status")) f.status = p.get("status")!;
  if (p.get("priority") && ["low", "medium", "high"].includes(p.get("priority")!)) f.priority = p.get("priority") as Priority;
  if (p.get("due")) f.due = p.get("due")!;
  return f;
}
function writeFilter(f: Filter) {
  const p = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => v && p.set(k, v));
  history.replaceState(null, "", p.size ? `?${p}` : location.pathname);
}

const welcome = "Hi! I’m your task assistant. I can create, find, edit, move, complete and delete tasks. Try “Create a high-priority task to finish the demo tomorrow” or “Show unfinished tasks”.";

function App() {
  const [tasks, setTasks] = useState<Task[]>(() => JSON.parse(localStorage.getItem("taskflow.tasks") || "[]"));
  const [messages, setMessages] = useState<ChatMessage[]>(() => JSON.parse(localStorage.getItem("taskflow.chat") || "[]"));
  const [draft, setDraft] = useState(() => localStorage.getItem("taskflow.draft") || "");
  const [filter, setFilter] = useState<Filter>(parseFilter);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Record<Status, boolean>>({ todo: false, progress: false, done: false });
  const [busy, setBusy] = useState(false);
  const [help, setHelp] = useState(false);
  const [clearOpen, setClearOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);
  const [pending, setPending] = useState<{ task?: Task; bulk?: Task[]; message: string; action: () => void } | null>(null);
  const [serverPrompt, setServerPrompt] = useState<PendingPrompt | null>(null);
  const [toast, setToast] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const taskLoadVersion = useRef(0);
  const apiHydrated = useRef(!USE_API);
  const sendingRef = useRef(false);

  useEffect(() => { if (apiHydrated.current) localStorage.setItem("taskflow.tasks", JSON.stringify(tasks)); }, [tasks]);
  useEffect(() => { if (apiHydrated.current) localStorage.setItem("taskflow.chat", JSON.stringify(messages)); }, [messages]);
  useEffect(() => localStorage.setItem("taskflow.draft", draft), [draft]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => { if (!USE_API && !messages.length) setMessages([{ id: "welcome", role: "assistant", text: welcome }]); }, []);
  useEffect(() => {
    if (!USE_API) return;
    const version = ++taskLoadVersion.current;
    Promise.all([
      fetch(`${API_BASE}/api/v1/tasks/?${new URLSearchParams(filter as Record<string, string>)}`).then((r) => r.ok ? r.json() : Promise.reject()),
      fetch(`${API_BASE}/api/v1/chat/messages/`).then((r) => r.ok ? r.json() : Promise.reject()),
    ]).then(([taskData, chatData]) => {
      if (version !== taskLoadVersion.current) return;
      setTasks(taskData.tasks.map((t: Task & { due?: string; createdAt: string; completedAt?: string; status: string }) => fromApiTask(t)));
      const history = chatData.messages.map((m: ChatMessage) => ({ id: String(m.id), role: m.role, text: m.text, kind: m.kind }));
      setMessages(history.length ? history : [{ id: "welcome", role: "assistant", text: welcome }]);
      setServerPrompt(chatData.pending_prompt || null);
      apiHydrated.current = true;
    }).catch(() => { apiHydrated.current = true; });
  }, []);

  const visible = useMemo(() => tasks.filter((t) => {
    if (filter.q && !`${t.title} ${t.description}`.toLowerCase().includes(filter.q.toLowerCase())) return false;
    if (filter.status === "open" && t.status === "done") return false;
    if (filter.status && filter.status !== "open" && t.status !== filter.status) return false;
    if (filter.priority && t.priority !== filter.priority) return false;
    if (filter.due === "none" && t.due) return false;
    if (filter.due === "overdue" && !(t.due && t.due < today() && t.status !== "done")) return false;
    return true;
  }), [tasks, filter]);
  const groups = (status: Status) => visible.filter((t) => t.status === status).sort((a, b) => {
    if (status === "done") return (b.completedAt || "").localeCompare(a.completedAt || "");
    if (!a.due && b.due) return 1; if (a.due && !b.due) return -1;
    if (a.due && b.due && a.due !== b.due) return a.due.localeCompare(b.due);
    return priorityRank[a.priority] - priorityRank[b.priority] || a.createdAt.localeCompare(b.createdAt);
  });
  const addMessage = (text: string, role: ChatMessage["role"] = "assistant", kind?: ChatMessage["kind"]) =>
    setMessages((m) => [...m, { id: crypto.randomUUID(), role, text, kind }]);
  const updateTask = (taskId: string, changes: Partial<Task>) => setTasks((list) => list.map((t) => t.id === taskId ? { ...t, ...changes } : t));
  const setStatus = async (task: Task, next: Status) => {
    if (task.status === next) { setToast(`“${task.title}” is already ${statusLabel[next]}. No change needed.`); return; }
    if (USE_API) {
      try {
        const response = await fetch(apiUrl(`/api/v1/tasks/${task.id}/status/`), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: toApiStatus(next) }),
        });
        if (!response.ok) throw new Error("Couldn't save that status change.");
        const saved = await response.json();
        updateTask(task.id, fromApiTask(saved));
        setToast(`Marked “${task.title}” ${next === "done" ? "Done" : `as ${statusLabel[next]}`}.`);
      } catch (error) { setToast(error instanceof Error ? error.message : "Couldn't save that change."); }
      return;
    }
    updateTask(task.id, { status: next, completedAt: next === "done" ? new Date().toISOString() : undefined });
    setToast(`Marked “${task.title}” ${next === "done" ? "Done" : `as ${statusLabel[next]}`}.`);
  };
  const candidates = (phrase: string) => {
    const q = phrase.toLowerCase().replace(/^(the|a|an)\s+/, "").trim();
    return tasks.filter((t) => `${t.title} ${t.description}`.toLowerCase().includes(q) || q.split(/\s+/).some((w) => w.length > 3 && t.title.toLowerCase().includes(w)));
  };
  const parseDue = (text: string) => {
    if (/tomorrow/i.test(text)) { const d = new Date(); d.setDate(d.getDate() + 1); return d.toISOString().slice(0, 10); }
    if (/today/i.test(text)) return today();
    const iso = text.match(/\b(20\d{2})-(\d{1,2})-(\d{1,2})\b/);
    if (iso) return `${iso[1]}-${iso[2].padStart(2, "0")}-${iso[3].padStart(2, "0")}`;
    return undefined;
  };
  const process = (raw: string) => {
    const text = raw.trim(); const lower = text.toLowerCase();
    if (!text) return;
    if (pending) {
      if (/^(cancel|no|never mind)\b/i.test(text)) { setPending(null); addMessage("Cancelled. Nothing was changed."); return; }
      if (/^(yes|confirm|y|do it|1)$/i.test(text)) { pending.action(); setPending(null); addMessage("Done — the confirmed change has been applied.", "assistant", "success"); return; }
      const n = Number(text);
      if (pending.bulk && n >= 1 && n <= pending.bulk.length) { const selected = pending.bulk[n - 1]; pending.action = () => setStatus(selected, selected.status === "done" ? "todo" : "done"); pending.action(); setPending(null); addMessage(`Done — updated “${selected.title}”.`, "assistant", "success"); return; }
      addMessage("Please reply with “yes” to confirm or “cancel” to leave everything unchanged.", "assistant", "question"); return;
    }
    if (/^(hi|hello|hey|what can you do|help)\b/i.test(text)) { addMessage(welcome); return; }
    if (/delete everything|delete all tasks/i.test(lower)) {
      if (!tasks.length) { addMessage("There are no tasks to delete."); return; }
      const snapshot = [...tasks]; setPending({ bulk: snapshot, message: `Delete all ${snapshot.length} tasks? This cannot be undone.`, action: () => setTasks([]) });
      addMessage(`I found ${snapshot.length} task${snapshot.length === 1 ? "" : "s"}. Delete all of them? This cannot be undone. Reply “yes” to confirm or “cancel”.`, "assistant", "question"); return;
    }
    if (/^delete\b|delete (the|my)\b/i.test(lower)) {
      const phrase = text.replace(/^delete\s+(the|my)?\s*/i, ""); const found = candidates(phrase);
      if (found.length !== 1) { addMessage(found.length ? `Which task did you mean?\n${found.slice(0, 5).map((t, i) => `${i + 1}. ${t.title} · ${statusLabel[t.status]}`).join("\n")}` : `I couldn't find “${phrase}”. Try the task's title.`, "assistant", "question"); return; }
      const target = found[0]; setPending({ task: target, message: `Delete “${target.title}”?`, action: () => setTasks((list) => list.filter((t) => t.id !== target.id)) });
      addMessage(`Delete “${target.title}”? This task will be removed. Reply “yes” to confirm or “cancel”.`, "assistant", "question"); return;
    }
    const nextStatus: Status | undefined = /in progress|started/i.test(lower) ? "progress" : /\b(done|complete|completed|finish|finished)\b/i.test(lower) ? "done" : /\b(to do|todo|reopen|back)\b/i.test(lower) ? "todo" : undefined;
    if (nextStatus && !/create|add|new task/i.test(lower)) {
      const phrase = text.replace(/^(move|mark|set|complete|finish|reopen|change)\b/i, "").replace(/\b(to|as|status)\s+(in progress|started|done|complete|completed|to do|todo)\b/i, "").replace(/\b(done|complete|completed|finish|finished|in progress|started|to do|todo)\b/i, "").replace(/\bthe\b/i, "").trim();
      const found = candidates(phrase);
      if (found.length !== 1) { addMessage(found.length ? `I found several possible tasks:\n${found.slice(0, 5).map((t, i) => `${i + 1}. ${t.title} · ${statusLabel[t.status]}`).join("\n")}\n\nWhich number should I use?` : `I couldn't find “${phrase}”. Try using more of the task title.`, "assistant", "question"); return; }
      const task = found[0]; const old = statusLabel[task.status]; const wasAlready = task.status === nextStatus;
      setStatus(task, nextStatus);
      addMessage(wasAlready ? `“${task.title}” is already ${old}. No change needed.` : `Done. I moved “${task.title}” from ${old} to ${statusLabel[nextStatus]}.`, "assistant", "success"); return;
    }
    if (/show|list|find|search|what tasks|unfinished|overdue/i.test(lower)) {
      const q = text.replace(/^(show|list|find|search)\s+(me\s+)?(all\s+)?/i, "").replace(/\b(tasks?|that are|related to|about)\b/gi, "").trim();
      const next: Filter = {};
      if (q && !/unfinished|overdue|high priority|priority/i.test(q)) next.q = q;
      if (/unfinished|open/i.test(lower)) next.status = "open";
      if (/overdue/i.test(lower)) next.due = "overdue";
      if (/high priority/i.test(lower)) next.priority = "high";
      setFilter(next); writeFilter(next);
      const result = tasks.filter((t) => (!next.q || `${t.title} ${t.description}`.toLowerCase().includes(next.q.toLowerCase())) && (!next.status || (next.status === "open" ? t.status !== "done" : t.status === next.status)) && (!next.priority || t.priority === next.priority) && (!next.due || (next.due === "overdue" && t.due! < today() && t.status !== "done")));
      addMessage(result.length ? `Found ${result.length} matching task${result.length === 1 ? "" : "s"}:\n${result.map((t) => `• ${t.title} · ${statusLabel[t.status]} · ${dateLabel(t.due, t.status)}`).join("\n")}` : "Nothing matched that search. Try a broader description.", "assistant", "success"); return;
    }
    if (/create|add|new task|make a task/i.test(lower)) {
        const title = escapeTitle(text
          .replace(/\b(due|tomorrow|today|high priority|medium priority|low priority|with description.*)$/i, "")
          .replace(/^(create|add|make|new)\s+(a\s+)?(task\s+)?(to\s+)?/i, ""));
      if (!title || title.length < 2) { addMessage("What should the task be called? Example: “Create a task to review the API.”", "assistant", "question"); return; }
      if (title.length > 200) { addMessage("That title is too long. Please keep titles to 200 characters or fewer.", "assistant", "error"); return; }
      const duplicate = tasks.find((t) => t.title.toLowerCase() === title.toLowerCase());
      if (duplicate) { addMessage(`A task named “${duplicate.title}” already exists. Would you like to create another?`, "assistant", "question"); return; }
      const priority: Priority = /high|urgent/i.test(lower) ? "high" : /medium/i.test(lower) ? "medium" : "low";
      const task: Task = { id: id(), title, description: "", status: /in progress/i.test(lower) ? "progress" : /done|complete/i.test(lower) ? "done" : "todo", priority, due: parseDue(text), createdAt: new Date().toISOString(), completedAt: /done|complete/i.test(lower) ? new Date().toISOString() : undefined };
      setTasks((list) => [...list, task]); setExpanded(task.id); setToast("Task created");
      addMessage(`Created “${task.title}” with ${priority} priority${task.due ? `, due ${fullDate(task.due)}` : ""}.`, "assistant", "success"); return;
    }
    if (/change|update|edit|make/i.test(lower) && /priority/i.test(lower)) {
      const priority: Priority = /high|urgent/i.test(lower) ? "high" : /medium/i.test(lower) ? "medium" : "low";
      const phrase = text.replace(/^(change|update|edit|make)\b/i, "").replace(/\bthe\b/i, "").replace(/\bpriority\b.*?\b(to|as)\b/i, "").replace(/\b(high|medium|low|urgent)\b/i, "").trim();
      const found = candidates(phrase);
      if (found.length !== 1) { addMessage(found.length ? `Which task did you mean?\n${found.map((t, i) => `${i + 1}. ${t.title} · ${statusLabel[t.status]}`).join("\n")}` : `I couldn't find “${phrase}”. Try the task's title.`, "assistant", "question"); return; }
      updateTask(found[0].id, { priority }); addMessage(`Updated “${found[0].title}” to ${priority} priority.`, "assistant", "success"); return;
    }
    addMessage("I can help with tasks: create, find, edit, move, complete, and delete. Try “Create a task to review the API” or “Show unfinished tasks”.", "assistant", "question");
  };
  const send = async (e?: FormEvent) => {
    e?.preventDefault(); if (!draft.trim() || draft.length > 1000 || busy || sendingRef.current) return;
    sendingRef.current = true;
    const text = draft.trim(); setDraft(""); addMessage(text, "user"); setBusy(true);
    if (USE_API) {
      try {
        const version = ++taskLoadVersion.current;
        const response = await fetch(`${API_BASE}/api/v1/chat/messages/`, {
          method: "POST", headers: { "Content-Type": "application/json", "X-Timezone": Intl.DateTimeFormat().resolvedOptions().timeZone },
          body: JSON.stringify({ client_message_id: crypto.randomUUID(), text }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "The assistant is unavailable.");
        data.assistant_messages?.forEach((m: ChatMessage) => addMessage(m.text, "assistant", m.kind));
        setServerPrompt(data.pending_prompt || null);
        if (data.filter) {
          setFilter(data.filter);
          writeFilter(data.filter);
        }
        const taskQuery = data.filter ? `?${new URLSearchParams(data.filter as Record<string, string>)}` : "";
        const taskData = await fetch(apiUrl(`/api/v1/tasks/${taskQuery}`)).then((r) => r.json());
        if (version !== taskLoadVersion.current) return;
        setTasks(taskData.tasks.map(fromApiTask));
      } catch (error) {
        const detail = error instanceof Error ? error.message : "The assistant is unavailable. No task was changed.";
        addMessage(detail.toLowerCase().includes("failed to fetch")
          ? `I couldn't reach the TaskFlow server. Confirm Django is running and retry.`
          : detail, "assistant", "error");
      } finally { sendingRef.current = false; setBusy(false); }
      return;
    }
    window.setTimeout(() => { process(text); sendingRef.current = false; setBusy(false); }, 280);
  };
  const toggle = (task: Task) => setStatus(task, task.status === "done" ? "todo" : "done");
  const loadSamples = async () => {
    if (USE_API) {
      try {
        const response = await fetch(apiUrl("/api/v1/tasks/sample/"), { method: "POST" });
        if (!response.ok) throw new Error("Couldn't load sample tasks.");
        const data = await response.json();
        setTasks(data.tasks.map(fromApiTask));
        addMessage("Loaded the sample tasks. You can ask me to move or edit any of them.", "assistant", "success");
      } catch (error) { setToast(error instanceof Error ? error.message : "Couldn't reach the TaskFlow server. Is Django running?"); }
      return;
    }
    setTasks((old) => { const titles = new Set(old.map((t) => t.title)); return [...old, ...sampleTitles.filter(([title]) => !titles.has(title)).map(([title, description, priority, status], i) => ({ id: `T-SAMPLE-${i + 1}`, title, description, priority, status, createdAt: new Date(Date.now() - i * 86400000).toISOString(), completedAt: status === "done" ? new Date().toISOString() : undefined }))]; });
    addMessage("Loaded the sample tasks. You can ask me to move or edit any of them.", "assistant", "success");
  };
  const clearFilter = () => { setFilter({}); writeFilter({}); };
  const answerPrompt = async (choice: "confirm" | "cancel") => {
    if (!serverPrompt) return;
    if (!USE_API) { setServerPrompt(null); return; }
    try {
      const response = await fetch(apiUrl(`/api/v1/chat/prompts/${serverPrompt.id}/answer/`), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ choice }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "That prompt is no longer active.");
      addMessage(data.text, "assistant", choice === "confirm" ? "success" : undefined);
      setServerPrompt(null);
      const taskData = await fetch(apiUrl("/api/v1/tasks/")).then((r) => r.json());
      setTasks(taskData.tasks.map(fromApiTask));
    } catch (error) { setToast(error instanceof Error ? error.message : "Couldn't answer the prompt."); }
  };

  return <div className="app">
    <header className="topbar"><div className="brand">TASKFLOW</div><div className="top-label">AI TASK MANAGER</div><button className="icon-btn" aria-label="What can I ask?" onClick={() => setHelp(true)}><CircleHelp size={21} /></button></header>
    <main className="layout">
      <section className="board-panel"><div className="eyebrow"><span className="eyebrow-dot" /> MY TASKS</div><h1>Organize your work,<br /><em>one message at a time.</em></h1><p className="intro">Your personal task board, powered by a little AI.</p>
        <div className="board-card"><div className="board-head"><div><h2>Task board <span>{tasks.length}</span></h2><p>{filter.q || filter.status || filter.priority ? "Showing filtered tasks" : "Everything you need to get done"}</p></div><ListFilter size={18} className="muted" /></div>
          {(filter.q || filter.status || filter.priority || filter.due) && <div className="filter-chip"><span><ListFilter size={13} /> {filter.q ? `Filtered: ${filter.q}` : filter.status === "open" ? "Unfinished tasks" : "Filtered tasks"}</span><button onClick={clearFilter}>Show all <X size={13} /></button></div>}
          {tasks.length === 0 ? <div className="empty"><div className="empty-icon"><FileText size={22} /></div><h3>Your board is clear</h3><p>Start by telling your assistant what you need to do.</p><button className="sample-btn" onClick={loadSamples}><Sparkles size={16} /> Load sample tasks</button></div> :
            <div className="groups">{(["todo", "progress", "done"] as Status[]).map((status) => { const list = groups(status); return <div className="group" key={status}><button className="group-head" onClick={() => setCollapsed((c) => ({ ...c, [status]: !c[status] }))}><span className={`chevron ${collapsed[status] ? "" : "open"}`}><ChevronDown size={16} /></span><strong>{statusLabel[status]}</strong><span className="group-count">{list.length}</span><span className="group-line" /></button>{!collapsed[status] && list.map((task) => <TaskRow key={task.id} task={task} expanded={expanded === task.id} onExpand={() => setExpanded(expanded === task.id ? null : task.id)} onToggle={() => toggle(task)} onDelete={() => setDeleteTarget(task)} />)}</div>; })}</div>}
        </div>
      </section>
      <section className="assistant-panel"><div className="assistant-head"><div className="assistant-title"><div className="assistant-avatar"><Sparkles size={18} /></div><div><h2>AI Assistant</h2><p>Manage everything with a message</p></div></div><button className="clear-btn" disabled={busy || messages.length <= 1} onClick={() => setClearOpen(true)}>Clear chat</button></div>
        <div className="chat"><div className="date-rule"><span>Today</span></div>{messages.map((m) => <div key={m.id} className={`message ${m.role} ${m.kind || ""}`}><div className="bubble">{m.text.split("\n").map((line, i) => <span key={i}>{line}{i < m.text.split("\n").length - 1 && <br />}</span>)}</div>{m.role === "assistant" && m.kind === "success" && <div className="view-link" onClick={() => document.querySelector(".board-card")?.scrollIntoView({ behavior: "smooth" })}>View updated task board <ChevronDown size={13} /></div>}</div>)}{busy && <div className="message assistant"><div className="bubble typing"><i /><i /><i /></div></div>}<div ref={endRef} /></div>
        {serverPrompt && <div className="prompt-actions"><span>{serverPrompt.kind === "choice" ? "Reply with a task number in the chat" : "Confirmation required"}</span>{serverPrompt.kind !== "choice" && <div><button className="secondary" onClick={() => answerPrompt("cancel")}>Cancel</button><button className="danger" onClick={() => answerPrompt("confirm")}>Confirm</button></div>}</div>}
        <form className="composer" onSubmit={send}><label htmlFor="instruction">YOUR INSTRUCTION</label><div className="input-wrap"><textarea id="instruction" value={draft} maxLength={1100} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder="Type a task instruction…" rows={1} /><button className="send-btn" disabled={!draft.trim() || draft.length > 1000 || busy} aria-label="Send"><Send size={17} /></button></div><div className="composer-foot"><span>e.g. “Complete the weekly report”</span>{draft.length > 800 && <span className={draft.length > 1000 ? "too-long" : ""}>{draft.length} / 1000</span>}</div></form>
      </section>
    </main>
    {help && <Modal title="What can I ask?" onClose={() => setHelp(false)}><p className="modal-intro">Talk to your task manager in plain English. Here are a few things you can try:</p><Prompt text="Create a high-priority task to finish the demo tomorrow" onClick={() => { setDraft("Create a high-priority task to finish the demo tomorrow"); setHelp(false); }} /><Prompt text="Show all unfinished tasks related to documentation" onClick={() => { setDraft("Show all unfinished tasks related to documentation"); setHelp(false); }} /><Prompt text="Move the demo task to In progress" onClick={() => { setDraft("Move the demo task to In progress"); setHelp(false); }} /><Prompt text="Delete the README task" onClick={() => { setDraft("Delete the README task"); setHelp(false); }} /><div className="tips"><b>Three things to know</b><span>Describe tasks in your own words.</span><span>I’ll ask when something is unclear.</span><span>Deleting always asks for confirmation.</span></div></Modal>}
    {clearOpen && <Modal title="Clear the chat?" onClose={() => setClearOpen(false)}><p>Your tasks won’t be affected. This only removes the conversation history.</p><div className="modal-actions"><button className="secondary" onClick={() => setClearOpen(false)}>Cancel</button><button className="danger" onClick={async () => { if (USE_API) await fetch(apiUrl("/api/v1/chat/messages/"), { method: "DELETE" }); setMessages([]); setClearOpen(false); }}>Clear chat</button></div></Modal>}
    {deleteTarget && <Modal title={`Delete “${deleteTarget.title}”?`} onClose={() => setDeleteTarget(null)}><p>This task will be removed from your board. This action cannot be undone.</p><div className="modal-actions"><button className="secondary" onClick={() => setDeleteTarget(null)}>Cancel</button><button className="danger" onClick={async () => { if (USE_API) { const response = await fetch(apiUrl(`/api/v1/tasks/${deleteTarget.id}/`), { method: "DELETE" }); if (!response.ok) { setToast("Couldn't delete that task."); return; } } setTasks((l) => l.filter((t) => t.id !== deleteTarget.id)); setDeleteTarget(null); setToast("Task deleted"); }}>Delete task</button></div></Modal>}
    {toast && <div className="toast"><Check size={15} /> {toast}<button onClick={() => setToast("")}><X size={14} /></button></div>}
    <footer><span><Zap size={13} /> Built for focused work</span><span>TaskFlow · Your tasks, your way</span></footer>
  </div>;
}

function TaskRow({ task, expanded, onExpand, onToggle, onDelete }: { task: Task; expanded: boolean; onExpand: () => void; onToggle: () => void; onDelete: () => void }) {
  const overdue = task.status !== "done" && !!task.due && task.due < today();
  return <div className={`task-row ${task.status === "done" ? "completed" : ""} ${expanded ? "expanded" : ""}`}><div className="task-main" onClick={onExpand}><button className={`complete-circle ${task.status === "done" ? "checked" : ""}`} onClick={(e) => { e.stopPropagation(); onToggle(); }} aria-label={task.status === "done" ? "Reopen task" : "Complete task"}>{task.status === "done" && <Check size={13} strokeWidth={3} />}</button><div className="task-copy"><div className="task-title">{task.title}</div><div className={`task-meta ${overdue ? "overdue" : ""}`}><Clock3 size={12} /> {dateLabel(task.due, task.status)} <span>·</span> {statusLabel[task.status]}</div></div></div><div className="task-actions"><span className={`priority ${task.priority}`}>{task.priority}</span><button className="delete-btn" onClick={onDelete} aria-label={`Delete ${task.title}`}><Trash2 size={15} /></button></div>{expanded && <div className="task-detail"><div><small>Description</small><p>{task.description || "No description"}</p></div><div><small>Due date</small><p>{fullDate(task.due)}</p></div><div><small>Task ID</small><p>{task.id}</p></div></div>}</div>;
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><div className="modal" role="dialog" aria-modal="true"><div className="modal-head"><h2>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>{children}</div></div>;
}
function Prompt({ text, onClick }: { text: string; onClick: () => void }) {
  return <button className="prompt" onClick={onClick}><MessageCircle size={15} /> {text}<ChevronUp size={14} /></button>;
}
export default App;
