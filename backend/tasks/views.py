import json
import os
import re
import uuid
from datetime import date, datetime, timedelta
from django.db import transaction
from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import ChatMessage, PendingPrompt, Task
from .serializers import ChatMessageSerializer, PendingPromptSerializer, TaskSerializer
from .ai import interpret
from .search import normalize_query, semantic_tasks

SAMPLES = [
    ("Finish AI presentation", "Prepare the final slides and rehearse the demo.", "high", "in_progress"),
    ("Review pull request #82", "Check the API changes and leave feedback.", "medium", "todo"),
    ("Send weekly report", "Summarize this week's progress for the team.", "high", "todo"),
    ("Update API documentation", "Document the new authentication endpoints.", "low", "todo"),
    ("Set up database", "Create the initial schema for the project.", "medium", "done"),
    ("Write project README", "Add setup steps and usage examples.", "low", "done"),
]

def resolve_due_phrase(value):
    if not value:
        return None, None
    phrase = str(value).strip().lower()
    today = timezone.localdate()
    if phrase == "today":
        return today, None
    if phrase == "tomorrow":
        return today + timedelta(days=1), None
    if phrase in {"next week", "next-week"}:
        return today + timedelta(days=(7 - today.weekday())), None
    weekday = next((index for index, name in enumerate(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    ) if name in phrase), None)
    if weekday is not None:
        delta = (weekday - today.weekday()) % 7 or 7
        return today + timedelta(days=delta), None
    day_first_match = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", phrase)
    if day_first_match:
        day, month, year = (int(part) for part in day_first_match.groups())
        try:
            return date(year, month, day), None
        except ValueError:
            return None, "That date does not exist. Use a valid date such as 26-10-2026."
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", phrase):
        try:
            return date.fromisoformat(phrase), None
        except ValueError:
            return None, "That date does not exist. Use a valid date such as 2026-11-12."
    return None, "I couldn't resolve that due date. Try today, tomorrow, Friday, DD-MM-YYYY, or YYYY-MM-DD."

def filtered_tasks(params=None):
    params = params or {}
    qs = Task.objects.filter(deleted_at__isnull=True)
    q, status, priority, due = (str(params.get(key, "")).strip() for key in ("q", "status", "priority", "due"))
    if q:
        matching = semantic_tasks(q, qs)
        qs = qs.filter(id__in=[task.id for task in matching])
    if status == "open":
        qs = qs.exclude(status=Task.Status.DONE)
    elif status in ("todo", "in-progress", "in_progress", "done"):
        qs = qs.filter(status=status.replace("-", "_"))
    if priority in ("low", "medium", "high"):
        qs = qs.filter(priority=priority)
    if due == "none":
        qs = qs.filter(due_date__isnull=True)
    elif due == "tomorrow":
        qs = qs.filter(due_date=timezone.localdate() + timedelta(days=1))
    elif due == "overdue":
        qs = qs.filter(due_date__lt=timezone.localdate()).exclude(status=Task.Status.DONE)
    elif due == "today":
        qs = qs.filter(due_date=timezone.localdate())
    elif due == "this-week":
        start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        qs = qs.filter(due_date__gte=start, due_date__lt=start + timedelta(days=7))
    return qs

def health(request):
    return JsonResponse({"status": "ok"})

def task_payload(qs):
    order = {"todo": 0, "in_progress": 1, "done": 2}
    tasks = list(qs)
    tasks.sort(key=lambda t: (order[t.status], -(t.completed_at.timestamp() if t.status == "done" and t.completed_at else 0), t.due_date is None, t.due_date or date.max, {"high": 0, "medium": 1, "low": 2}[t.priority], t.created_at))
    return TaskSerializer(tasks, many=True).data

@api_view(["GET"])
def tasks(request):
    q, status, priority, due = request.GET.get("q", "").strip(), request.GET.get("status"), request.GET.get("priority"), request.GET.get("due")
    qs = filtered_tasks(request.GET)
    return Response({"tasks": task_payload(qs), "count": qs.count(), "filter": {k: v for k, v in {"q": q, "status": status, "priority": priority, "due": due}.items() if v}})

@api_view(["POST"])
def sample_tasks(request):
    existing = set(Task.objects.filter(deleted_at__isnull=True).values_list("title", flat=True))
    created = []
    for title, description, priority, status in SAMPLES:
        if title not in existing:
            created.append(Task.objects.create(title=title, description=description, priority=priority, status=status, completed_at=timezone.now() if status == "done" else None))
    return Response({"tasks": task_payload(Task.objects.filter(deleted_at__isnull=True)), "created": len(created)})

@api_view(["POST"])
def task_status(request, task_id):
    status = request.data.get("status")
    if status not in ("todo", "in_progress", "done"): return Response({"code": "validation_error", "detail": "Status must be todo, in_progress, or done."}, status=400)
    try:
        with transaction.atomic():
            task = Task.objects.select_for_update().get(pk=task_id, deleted_at__isnull=True)
            task.status, task.completed_at = status, timezone.now() if status == "done" else None
            task.save(update_fields=["status", "completed_at"])
    except Task.DoesNotExist: return Response({"code": "task_not_found", "detail": "Task not found."}, status=404)
    return Response(TaskSerializer(task).data)

@api_view(["PATCH", "DELETE"])
def task_detail(request, task_id):
    try: task = Task.objects.get(pk=task_id, deleted_at__isnull=True)
    except Task.DoesNotExist: return Response({"code": "task_not_found", "detail": "Task not found."}, status=404)
    if request.method == "PATCH":
        if set(request.data) - {"title", "description", "priority", "due"}:
            return Response({"code": "validation_error", "detail": "Only title, description, priority, and due can be edited."}, status=400)
        if "title" in request.data:
            title = str(request.data["title"]).strip()
            if not title or len(title) > 200:
                return Response({"code": "validation_error", "detail": "Title must be 1–200 characters."}, status=400)
            task.title = title
        if "description" in request.data:
            description = str(request.data["description"])
            if len(description) > 1000:
                return Response({"code": "validation_error", "detail": "Description must be at most 1,000 characters."}, status=400)
            task.description = description
        if "priority" in request.data:
            if request.data["priority"] not in dict(Task.Priority.choices):
                return Response({"code": "validation_error", "detail": "Priority must be low, medium, or high."}, status=400)
            task.priority = request.data["priority"]
        if "due" in request.data:
            if request.data["due"] in ("", None):
                task.due_date = None
            else:
                try:
                    task.due_date = date.fromisoformat(str(request.data["due"]))
                except ValueError:
                    return Response({"code": "validation_error", "detail": "Due date must be YYYY-MM-DD or null."}, status=400)
        task.save()
        return Response(TaskSerializer(task).data)
    task.deleted_at = timezone.now(); task.save(update_fields=["deleted_at"])
    return Response({"deleted": True, "task_id": str(task.id)})

@api_view(["POST"])
def bulk_tasks(request):
    task_ids = request.data.get("task_ids") or []
    changes = request.data.get("changes") or {}
    if not task_ids:
        return Response({"code": "validation_error", "detail": "task_ids must not be empty."}, status=400)
    if set(changes) - {"status", "priority"}:
        return Response({"code": "validation_error", "detail": "Bulk changes support status and priority only."}, status=400)
    if changes.get("status") not in (None, "todo", "in_progress", "done") or changes.get("priority") not in (None, "low", "medium", "high"):
        return Response({"code": "validation_error", "detail": "Invalid bulk status or priority."}, status=400)
    selected = Task.objects.filter(id__in=task_ids, deleted_at__isnull=True)
    for task in selected:
        if "status" in changes:
            task.status = changes["status"]
            task.completed_at = timezone.now() if task.status == "done" else None
        if "priority" in changes:
            task.priority = changes["priority"]
        task.save()
    return Response({"tasks": task_payload(selected), "updated": selected.count()})

@api_view(["POST"])
def bulk_preview(request):
    selected = filtered_tasks(request.data.get("filter") or {})
    return Response({"count": selected.count(), "tasks": task_payload(selected)})

def resolve_title_candidates(phrase, tasks):
    phrase = phrase.strip().strip("\"'“”").strip()
    words = [word for word in re.findall(r"[a-z0-9#]+", phrase.lower())
             if word not in {"the", "a", "an", "my", "task", "tasks", "straight", "back"}]
    if not words:
        return []
    exact_title = tasks.filter(title__iexact=phrase)
    if exact_title.exists():
        return list(exact_title[:5])
    exact = tasks.filter(title__icontains=" ".join(words))
    if exact.exists():
        return list(exact[:5])
    matches = [task for task in tasks if any(word in task.title.lower() for word in words)]
    return matches[:5]

def parse_create_command(text):
    body = re.sub(r"^(create|add|make|new)(\s+a)?(\s+task)?(\s+called|\s+named)?(\s+to)?\s*", "", text, flags=re.I).strip()
    priority = "high" if re.search(r"\b(high|urgent|important|importent)[-\s]+priority\b", body, re.I) else "medium" if re.search(r"\bmedium[-\s]+priority\b", body, re.I) else "low"
    body = re.sub(r"\b(high|medium|low|urgent|important|importent)[-\s]+priority\b", "", body, flags=re.I).strip()
    body = re.sub(r"^(?:a\s+)?task\s+", "", body, flags=re.I)
    due_match = re.search(
        r"\b(?:due(?:\s+date)?\s+)?"
        r"(today|tomorrow|next week|next-week|\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{4}-\d{2}-\d{2})\b",
        body,
        re.I,
    )
    due_phrase = due_match.group(1).lower() if due_match else None
    description = ""
    if due_match:
        before, after = body[:due_match.start()], body[due_match.end():]
        body = before.strip()
        description = after.strip()
        body = re.sub(r"\bdue\s+date\s*$", "", body, flags=re.I).strip()
    description_match = re.search(r"\b(?:with|and with)\s+(?:the\s+)?description\s*:?\s*(.+)$", body, re.I)
    if description_match:
        description = description_match.group(1).strip()
        body = body[:description_match.start()].strip()
    title = re.sub(r"^(called|named)\s+", "", body, flags=re.I).strip(" .:-")
    title = re.sub(r"\s+", " ", title)
    return title, description, due_phrase, priority

def normalized_message(text):
    return re.sub(r"\s+", " ", text).strip().casefold()

def duplicate_create_response(task):
    if task.created_at >= timezone.now() - timedelta(seconds=15):
        return "success", f"Done. I created “{task.title}” as {task.priority.title()} priority."
    return "success", f"“{task.title}” already exists. I did not create a duplicate."

def local_command(text):
    lower = text.lower()
    normalized_status_text = re.sub(r"\bin[-\s]+progress\b", "in progress", text, flags=re.I)
    lower = normalized_status_text.lower()
    tasks = Task.objects.filter(deleted_at__isnull=True)
    if re.search(r"^(show|list|find|search)", lower):
        q = re.sub(r"^(show|list|find|search)( me)?( all)?( tasks?)?", "", text, flags=re.I).strip()
        raw_query = q
        due_filter = (
            "today" if re.search(r"\btoday(?:'s)?\b", lower)
            else "tomorrow" if re.search(r"\btomorrow\b", lower)
            else "none" if re.search(r"\b(no|without| missing)\s+due\s+date\b|\bno[-\s]+due\b", lower)
            else None
        )
        if due_filter == "today":
            raw_query = re.sub(r"\btoday(?:'s)?\b", "", raw_query, flags=re.I).strip()
        elif due_filter == "tomorrow":
            raw_query = re.sub(r"\btomorrow\b", "", raw_query, flags=re.I).strip()
        elif due_filter == "none":
            raw_query = re.sub(r"\b(no|without| missing)\s+due\s+date\b|\bno[-\s]+due\b", "", raw_query, flags=re.I).strip()
        q = normalize_query(raw_query)
        due_date = timezone.localdate() if due_filter == "today" else timezone.localdate() + timedelta(days=1) if due_filter == "tomorrow" else None
        if due_filter == "none":
            tasks = tasks.filter(due_date__isnull=True)
        elif due_date:
            tasks = tasks.filter(due_date=due_date)
        if re.search(r"\b(completed|done)\b", lower):
            found = tasks.filter(status=Task.Status.DONE)
        elif re.search(r"\b(unfinished|open)\b", lower):
            found = tasks.exclude(status=Task.Status.DONE)
        elif re.search(r"\b(high|urgent|medium|low)[-\s]+priority\b", lower):
            priority = "high" if re.search(r"\b(high|urgent)", lower) else "medium" if "medium" in lower else "low"
            found = tasks.filter(priority=priority)
        elif re.search(r"\boverdue\b", lower):
            found = tasks.filter(due_date__lt=timezone.localdate()).exclude(status=Task.Status.DONE)
        else:
            found = semantic_tasks(q, tasks) if q else list(tasks)
        found_list = list(found)
        return "success", f"Found {len(found_list)} task(s).", found_list, None
    if re.search(r"^(delete|remove)\b", lower):
        phrase = re.sub(r"^(delete|remove)( the| my)?\s*", "", text, flags=re.I).strip().strip("\"'“”").strip()
        found = resolve_title_candidates(phrase, tasks)
        if len(found) != 1:
            return "question", "Which task(s) should I delete?", found, {"operation": "delete"}
        return "question", f"Delete “{found[0].title}”? This task will be removed.", [found[0]], None
    if re.search(r"\b(change|update|edit).*\bpriority\b", lower):
        priority = "high" if "high" in lower or "urgent" in lower else "medium" if "medium" in lower else "low"
        match = re.search(r"priority\s+(?:of|for)\s+(.+?)\s+(?:to|as)\s+(?:high|medium|low|urgent)", text, re.I)
        phrase = match.group(1).strip() if match else re.sub(r"\b(high|medium|low|urgent|priority|to|as)\b", "", text, flags=re.I).strip()
        found = resolve_title_candidates(phrase, tasks)
        if len(found) != 1:
            return "question", "Which task should I update?", found, {"operation": "priority", "priority": priority}
        task = Task.objects.select_for_update().get(pk=found[0].pk, deleted_at__isnull=True)
        task.priority = priority
        task.save(update_fields=["priority"])
        return "success", f"Done. I changed “{task.title}” to {priority.title()} priority.", [task], [str(task.id)]
    if re.search(r"create|add|new task", lower):
        title, description, due_phrase, priority = parse_create_command(text)
        if not title: return "question", "What should the task be called?", [], None
        due, due_error = resolve_due_phrase(due_phrase)
        if due_error:
            return "error", due_error, [], None
        duplicate = tasks.filter(description__iexact=description[:1000], due_date=due, priority=priority).filter(
            title__iexact=title[:200]
        ).first()
        if not duplicate:
            normalized_title = re.sub(r"^task\s+", "", title[:200], flags=re.I)
            duplicate = next(
                (candidate for candidate in tasks.filter(description__iexact=description[:1000], due_date=due, priority=priority)
                 if re.sub(r"^task\s+", "", candidate.title, flags=re.I).casefold() == normalized_title.casefold()),
                None,
            )
        if duplicate:
            message_kind, message = duplicate_create_response(duplicate)
            return message_kind, message, [duplicate], None
        task = Task.objects.create(title=title[:200], description=description[:1000], priority=priority, due_date=due)
        return "success", f"Done. I created “{task.title}” as {priority.title()} priority.", [task], [str(task.id)]
    if re.search(r"\b(in progress|started|done|complete|completed|finish|finished|reopen|to do|todo)\b", lower):
        desired = "in_progress" if re.search(r"\b(in progress|started)\b", lower) else "todo" if re.search(r"\b(reopen|to do|todo)\b", lower) else "done"
        phrase = re.sub(r"^(complete|finish|finished|mark|move|reopen|set|change|update)\b\s*", "", normalized_status_text, flags=re.I)
        phrase = re.sub(r"\b(to|as|straight to)\s+(in progress|started|done|complete|completed|to do|todo)\b", "", phrase, flags=re.I)
        phrase = re.sub(r"\b(in progress|started|done|complete|completed|finish|finished|reopen|to do|todo)\b", "", phrase, flags=re.I)
        found = resolve_title_candidates(phrase, tasks)
        if len(found) != 1:
            return "question", "Which task should I update?", found, {"operation": "status", "status": desired}
        task = found[0]
        old = task.get_status_display()
        if task.status == desired:
            return "success", f"“{task.title}” is already {old}. No change needed.", [task], None
        task.status, task.completed_at = desired, timezone.now() if desired == "done" else None
        task.save(update_fields=["status", "completed_at"])
        return "success", f"Done. I moved “{task.title}” from {old} to {task.get_status_display()}.", [task], [str(task.id)]
    return "question", "I can create, find, move, complete, edit, and delete tasks. Try “Create a task to review the API”.", [], None

@api_view(["GET", "POST", "DELETE"])
def chat_messages(request):
    if request.method == "GET":
        prompt = PendingPrompt.objects.filter(
            resolved_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("-created_at").first()
        history = list(ChatMessage.objects.order_by("-created_at")[:50])
        history.reverse()
        return Response({
            "messages": ChatMessageSerializer(history, many=True).data,
            "pending_prompt": PendingPromptSerializer(prompt).data if prompt else None,
        })
    if request.method == "DELETE":
        ChatMessage.objects.all().delete()
        return Response({"cleared": True})
    text = str(request.data.get("text", "")).strip()
    client_id = request.data.get("client_message_id")
    if not text or len(text) > 1000: return Response({"code": "validation_error", "detail": "Message must be between 1 and 1000 characters."}, status=400)
    if client_id:
        try:
            client_id = uuid.UUID(str(client_id))
        except ValueError:
            return Response({"code": "validation_error", "detail": "client_message_id must be a UUID."}, status=400)
    if client_id:
        existing = ChatMessage.objects.filter(client_message_id=client_id, role="user").first()
        if existing:
            reply = ChatMessage.objects.filter(created_at__gte=existing.created_at, role="assistant").first()
            return Response({"user_message": ChatMessageSerializer(existing).data, "assistant_messages": [ChatMessageSerializer(reply).data] if reply else []})
    if re.search(r"\b(create|add|make|new)\b", text, re.I):
        recent_user = next(
            (
                message for message in ChatMessage.objects.filter(
                    role="user",
                    created_at__gte=timezone.now() - timedelta(seconds=10),
                ).order_by("-created_at")
                if normalized_message(message.text) == normalized_message(text)
            ),
            None,
        )
        if recent_user:
            recent_reply = ChatMessage.objects.filter(
                role="assistant",
                created_at__gte=recent_user.created_at,
            ).order_by("created_at").first()
            if recent_reply:
                return Response({
                    "user_message": ChatMessageSerializer(recent_user).data,
                    "assistant_messages": [ChatMessageSerializer(recent_reply).data],
                    "changed_task_ids": [],
                })
    with transaction.atomic():
        user = ChatMessage.objects.create(client_message_id=client_id, role="user", kind="user", text=text)
        pending_prompt = None
        active_prompt = PendingPrompt.objects.filter(
            resolved_at__isnull=True, expires_at__gt=timezone.now()
        ).order_by("-created_at").first()
        if active_prompt and active_prompt.kind == PendingPrompt.Kind.CHOICE and re.fullmatch(r"\s*\d+(?:\s*(?:,|and)\s*\d+)*\s*", text, re.I):
            indexes = [int(value) - 1 for value in re.findall(r"\d+", text)]
            candidate_ids = active_prompt.action.get("candidate_ids", [])
            if not indexes or any(index < 0 or index >= len(candidate_ids) for index in indexes):
                reply = ChatMessage.objects.create(role="assistant", kind="question", text="Please choose one of the listed task numbers.")
                return Response({"user_message": ChatMessageSerializer(user).data, "assistant_messages": [ChatMessageSerializer(reply).data], "pending_prompt": PendingPromptSerializer(active_prompt).data})
            operation = active_prompt.action.get("operation")
            selected_tasks = list(Task.objects.filter(id__in=[candidate_ids[index] for index in indexes], deleted_at__isnull=True))
            if len(selected_tasks) != len(indexes) or operation not in {"status", "priority", "delete"}:
                return Response({"code": "prompt_invalid", "detail": "That task is no longer available."}, status=409)
            if operation == "delete":
                question = f"Delete {len(selected_tasks)} selected task(s)? This cannot be undone."
                prompt = PendingPrompt.objects.create(
                    kind=PendingPrompt.Kind.CONFIRM,
                    question=question,
                    action={"task_ids": [str(selected.id) for selected in selected_tasks], "delete": True, "changes": {}},
                    expires_at=timezone.now() + timedelta(minutes=5),
                )
                active_prompt.outcome = f"Selected {len(selected_tasks)} task(s) for deletion."
                active_prompt.resolved_at = timezone.now()
                active_prompt.save(update_fields=["outcome", "resolved_at"])
                reply = ChatMessage.objects.create(
                    role="assistant",
                    kind="question",
                    text=f"{question} Reply “yes” to confirm or “cancel”.",
                )
                return Response({
                    "user_message": ChatMessageSerializer(user).data,
                    "assistant_messages": [ChatMessageSerializer(reply).data],
                    "pending_prompt": PendingPromptSerializer(prompt).data,
                })
            if operation == "status":
                for selected in selected_tasks:
                    selected.status = active_prompt.action["status"]
                    selected.completed_at = timezone.now() if selected.status == "done" else None
                    selected.save(update_fields=["status", "completed_at"])
                outcome = f"Done. Updated {len(selected_tasks)} task(s) to {selected_tasks[0].get_status_display()}."
            else:
                for selected in selected_tasks:
                    selected.priority = active_prompt.action["priority"]
                    selected.save(update_fields=["priority"])
                outcome = f"Done. Updated {len(selected_tasks)} task(s) to {selected_tasks[0].get_priority_display()} priority."
            active_prompt.outcome = outcome
            active_prompt.resolved_at = timezone.now()
            active_prompt.save(update_fields=["outcome", "resolved_at"])
            reply = ChatMessage.objects.create(role="assistant", kind="success", text=outcome)
            return Response({"user_message": ChatMessageSerializer(user).data, "assistant_messages": [ChatMessageSerializer(reply).data], "changed_task_ids": [str(selected.id) for selected in selected_tasks]})
        if active_prompt and text.lower() in {"yes", "y", "confirm", "ok", "cancel", "cencel", "cancelled", "never mind", "stop", "no", "n"}:
            if text.lower() in {"cancel", "cencel", "cancelled", "never mind", "stop", "no", "n"}:
                active_prompt.outcome = "Cancelled. Nothing was changed."
            else:
                task_ids = active_prompt.action.get("task_ids", [])
                Task.objects.filter(id__in=task_ids, deleted_at__isnull=True).update(deleted_at=timezone.now())
                active_prompt.outcome = f"Done. Deleted {len(task_ids)} task(s)."
            active_prompt.resolved_at = timezone.now()
            active_prompt.save(update_fields=["outcome", "resolved_at"])
            reply = ChatMessage.objects.create(role="assistant", kind="success", text=active_prompt.outcome)
            return Response({"user_message": ChatMessageSerializer(user).data, "assistant_messages": [ChatMessageSerializer(reply).data], "changed_task_ids": active_prompt.action.get("task_ids", [])})
        try:
            ai_action = None
            handled_fallback = False
            ai_action = interpret(text)
        except Exception:
            # Greetings and capability questions do not need an AI call. Mutating
            # instructions still fail closed so an unavailable provider cannot
            # leave the task store in an uncertain state.
            if re.match(r"^(hi|hello|hey|help|what can you do)\b", text, re.I):
                kind, reply_text, changed, changed_ids = "question", (
                    "I can create, find, edit, move, complete, and delete tasks. "
                    "Try “Create a task to review the API”."
                ), [], None
                handled_fallback = True
            elif settings.DEBUG:
                # Local development remains usable when a provider key is
                # missing, expired, or rate-limited. Production still fails
                # closed so an AI outage cannot partially apply a request.
                kind, reply_text, changed, changed_ids = local_command(text)
                handled_fallback = True
            else:
                return Response({"code": "ai_unavailable", "detail": "The AI service is unavailable. No task was changed."}, status=503)
        explicit_status_command = (
            re.search(r"\b(move|mark|set|complete|finish|reopen|update)\b", text, re.I)
            and re.search(r"\b(in[-\s]+progress|started|done|complete|completed|finished|to do|todo)\b", text, re.I)
        )
        if handled_fallback:
            pass
        elif ai_action and not explicit_status_command:
            kind, reply_text, changed, changed_ids = execute_ai_action(ai_action)
        else:
            kind, reply_text, changed, changed_ids = local_command(text)
        prompt_action = (changed_ids if isinstance(changed_ids, dict) else None)
        candidate_ids = [str(task.id) for task in changed] if changed else []
        if kind == "question" and prompt_action and candidate_ids:
            pending_prompt = PendingPrompt.objects.create(
                kind=PendingPrompt.Kind.CHOICE,
                question=reply_text,
                action={**prompt_action, "candidate_ids": candidate_ids},
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            reply_text = f"{reply_text}\n" + "\n".join(
                f"{index}. {task.title} · {task.get_status_display()}" for index, task in enumerate(changed, 1)
            ) + "\n\nReply with the task number."
        elif kind == "question" and (
            re.search(r"\b(delete|remove)\b", text, re.I)
            or (ai_action and ai_action.get("kind") in {"bulk_delete", "bulk_update"})
        ):
            prompt = PendingPrompt.objects.create(
                kind=PendingPrompt.Kind.CONFIRM,
                question=reply_text,
                action={
                    "task_ids": changed_ids or [str(task.id) for task in changed],
                    "changes": (ai_action or {}).get("changes", {}),
                    "delete": ai_action is None or (ai_action or {}).get("kind") in {"delete", "bulk_delete"},
                },
                expires_at=timezone.now() + timedelta(minutes=5),
            )
            pending_prompt = prompt
            reply_text = f"{reply_text} Reply “yes” to confirm or “cancel”."
        reply = ChatMessage.objects.create(role="assistant", kind=kind, text=reply_text)
    result_filter = None
    if ai_action and ai_action.get("kind") == "search":
        search_filter = ai_action.get("filter") or {}
        result_filter = {
            key: value for key, value in {
                "q": search_filter.get("q") or ai_action.get("query"),
                "status": search_filter.get("status"),
                "priority": search_filter.get("priority"),
                "due": search_filter.get("due"),
            }.items() if value
        }
    elif not ai_action and kind == "success" and re.search(r"^(show|list|find|search)", text, re.I):
        search_text = re.sub(r"^(show|list|find|search)( me)?( all)?( tasks?)?", "", text, flags=re.I).strip()
        search_text = re.sub(r"^(tasks?\s+)?(related to|about|that are)\s+", "", search_text, flags=re.I).strip()
        result_filter = {
            key: value for key, value in {
                "q": None if re.search(r"\b(high|urgent|medium|low)[-\s]+priority\b|\b(completed|done|unfinished|open|overdue|today(?:'s)?|tomorrow|no[-\s]+due|without\s+due\s+date)\b", text, re.I) else normalize_query(search_text),
                "status": "done" if re.search(r"\b(completed|done)\b", text, re.I) else "open" if re.search(r"\b(unfinished|open)\b", text, re.I) else None,
                "priority": "high" if re.search(r"\b(high|urgent)[-\s]+priority\b", text, re.I) else "medium" if re.search(r"\bmedium[-\s]+priority\b", text, re.I) else "low" if re.search(r"\blow[-\s]+priority\b", text, re.I) else None,
                "due": "overdue" if re.search(r"\boverdue\b", text, re.I) else "today" if re.search(r"\btoday(?:'s)?\b", text, re.I) else "tomorrow" if re.search(r"\btomorrow\b", text, re.I) else "none" if re.search(r"\b(no|without| missing)\s+due\s+date\b|\bno[-\s]+due\b", text, re.I) else None,
            }.items() if value
        }
    return Response({"user_message": ChatMessageSerializer(user).data, "assistant_messages": [ChatMessageSerializer(reply).data], "changed_task_ids": changed_ids if isinstance(changed_ids, list) else [], "filter": result_filter, "pending_prompt": PendingPromptSerializer(pending_prompt).data if pending_prompt else None})

@api_view(["POST"])
def prompt_answer(request, prompt_id):
    try:
        prompt = PendingPrompt.objects.get(pk=prompt_id)
    except PendingPrompt.DoesNotExist:
        return Response({"code": "prompt_not_found", "detail": "That prompt no longer exists."}, status=404)
    if prompt.resolved_at or prompt.expires_at <= timezone.now():
        return Response({"code": "prompt_expired", "detail": "That prompt has expired. Nothing was changed."}, status=409)
    choice = str(request.data.get("choice", "")).lower().strip()
    if choice in {"cancel", "no", "n"}:
        prompt.outcome = "Cancelled. Nothing was changed."
        prompt.resolved_at = timezone.now()
        prompt.save(update_fields=["outcome", "resolved_at"])
        return Response({"text": prompt.outcome, "changed_task_ids": []})
    if choice not in {"confirm", "yes", "y", "ok"}:
        return Response({"code": "validation_error", "detail": "Answer with confirm or cancel."}, status=400)
    task_ids = prompt.action.get("task_ids", [])
    selected = Task.objects.filter(id__in=task_ids, deleted_at__isnull=True)
    if prompt.action.get("delete"):
        selected.update(deleted_at=timezone.now())
        prompt.outcome = f"Done. Deleted {len(task_ids)} task(s)."
    else:
        changes = prompt.action.get("changes", {})
        for task in selected:
            if changes.get("status"):
                task.status = changes["status"]
                task.completed_at = timezone.now() if task.status == "done" else None
            if changes.get("priority"):
                task.priority = changes["priority"]
            task.save()
        prompt.outcome = f"Done. Updated {len(task_ids)} task(s)."
    prompt.resolved_at = timezone.now()
    prompt.save(update_fields=["outcome", "resolved_at"])
    return Response({"text": prompt.outcome, "changed_task_ids": task_ids})

def execute_ai_action(action):
    kind = action.get("kind")
    tasks = Task.objects.filter(deleted_at__isnull=True)
    if kind in {"bulk_delete", "bulk_update"}:
        selected = filtered_tasks(action.get("filter") or {})
        changes = action.get("changes") or {}
        if not selected.exists():
            return "success", "Nothing matched that bulk action.", [], None
        verb = "delete" if kind == "bulk_delete" else "update"
        detail = f"Preview: {selected.count()} task(s) will be affected. Reply “yes” to {verb} them or “cancel”."
        return "question", detail, list(selected), [str(task.id) for task in selected]
    if kind == "create":
        title = (action.get("title") or "").strip()
        if not title or len(title) > 200:
            return "error", "Please provide a task title of 1–200 characters.", [], None
        priority = action.get("priority") or "low"
        if priority not in dict(Task.Priority.choices):
            return "error", "Priority must be low, medium, or high.", [], None
        if tasks.filter(title__iexact=title).exists():
            return "question", f"“{title}” already exists. Should I create another?", [], None
        due, due_error = resolve_due_phrase(action.get("due"))
        if due_error:
            return "error", due_error, [], None
        description = str(action.get("description") or "").strip()
        if len(description) > 1000:
            return "error", "Description must be at most 1,000 characters.", [], None
        duplicate = tasks.filter(title__iexact=title, description__iexact=description, due_date=due, priority=priority).first()
        if duplicate:
            message_kind, message = duplicate_create_response(duplicate)
            return message_kind, message, [duplicate], None
        task = Task.objects.create(title=title, description=description, priority=priority, due_date=due)
        return "success", f"Done. I created “{title}” as {priority.title()} priority.", [task], [str(task.id)]
    if kind == "search":
        filters = action.get("filter") or {}
        selected = filtered_tasks(filters)
        query = (filters.get("q") or action.get("query") or "").strip()
        found = semantic_tasks(query, selected) if query else list(selected)
        return "success", f"Found {len(found)} matching task(s).", list(found), None
    phrase = (action.get("title") or action.get("query") or "").strip()
    found = tasks.filter(title__icontains=phrase)
    if found.count() != 1:
        operation = "status" if kind == "status" else "priority" if action.get("priority") else None
        if kind == "delete":
            operation = "delete"
        metadata = {"operation": operation, "status": action.get("status")} if operation == "status" else {"operation": operation, "priority": action.get("priority")} if operation else None
        return "question", "I need a clearer task reference before changing anything.", list(found[:5]), metadata
    task = Task.objects.select_for_update().get(pk=found.first().pk, deleted_at__isnull=True)
    if kind == "status":
        status = action.get("status")
        if status not in dict(Task.Status.choices):
            return "error", "That status is not supported. Use To do, In progress, or Done.", [], None
        task.status, task.completed_at = status, timezone.now() if status == "done" else None
        task.save(update_fields=["status", "completed_at"])
        return "success", f"Done. I moved “{task.title}” to {task.get_status_display()}.", [task], [str(task.id)]
    if kind == "update":
        changed = []
        if action.get("title") is not None:
            title = str(action["title"]).strip()
            if not title or len(title) > 200:
                return "error", "Title must be between 1 and 200 characters.", [], None
            task.title = title
            changed.append("title")
        if action.get("description") is not None:
            description = str(action["description"])
            if len(description) > 1000:
                return "error", "Description must be at most 1,000 characters.", [], None
            task.description = description
            changed.append("description")
        if action.get("priority") is not None:
            if action["priority"] not in dict(Task.Priority.choices):
                return "error", "Priority must be low, medium, or high.", [], None
            task.priority = action["priority"]
            changed.append("priority")
        if action.get("clear_due"):
            task.due_date = None
            changed.append("due date")
        if action.get("due"):
            due, due_error = resolve_due_phrase(action["due"])
            if due_error:
                return "error", due_error, [], None
            task.due_date = due
            changed.append("due date")
        task.save()
        return "success", f"Done. Updated “{task.title}” ({', '.join(changed) or 'no fields changed'}).", [task], [str(task.id)]
    if kind == "delete":
        return "question", f"Delete “{task.title}”? Reply with confirmation before I remove it.", [task], None
    return "question", "I can create, find, move, complete, edit, and delete tasks.", [], None
