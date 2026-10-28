import uuid
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone
from .models import ChatMessage, PendingPrompt, Task


class TaskFlowApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def chat(self, text):
        return self.client.post(
            "/api/v1/chat/messages/",
            {"client_message_id": str(uuid.uuid4()), "text": text},
            format="json",
        )

    @patch("tasks.views.interpret", return_value=None)
    def test_create_and_list_persist(self, _interpret):
        response = self.chat("Create a high priority task to review the API")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Task.objects.first().priority, "high")
        listed = self.client.get("/api/v1/tasks/")
        self.assertEqual(listed.data["count"], 1)

    @patch("tasks.views.interpret", return_value=None)
    def test_create_extracts_title_description_and_due_date(self, _interpret):
        response = self.chat(
            "Add a task meeting for new project tomorrow our all team member "
            "conducting a meeting for our new project where we will discuss about the PRD of our new project"
        )
        self.assertEqual(response.status_code, 200)
        task = Task.objects.get()
        self.assertEqual(task.title, "meeting for new project")
        self.assertEqual(
            task.description,
            "our all team member conducting a meeting for our new project where we will discuss about the PRD of our new project",
        )
        self.assertEqual(task.due_date, timezone.localdate() + timedelta(days=1))

    @patch("tasks.views.interpret", return_value=None)
    def test_create_extracts_day_first_numeric_due_date(self, _interpret):
        response = self.chat("add a task Create the Api documentation due date 26-10-2026")
        self.assertEqual(response.status_code, 200)
        task = Task.objects.get()
        self.assertEqual(task.title, "Create the Api documentation")
        self.assertEqual(task.description, "")
        self.assertEqual(task.due_date.isoformat(), "2026-10-26")

    @patch("tasks.views.interpret", return_value=None)
    def test_repeated_create_does_not_duplicate_task(self, _interpret):
        text = "Add a task meeting for new project tomorrow our all team member"
        self.chat(text)
        second = self.chat(text)
        self.assertEqual(Task.objects.count(), 1)
        self.assertIn("Done. I created", second.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_priority_before_task_does_not_change_title(self, _interpret):
        response = self.chat(
            "Add a high priority task meeting for new project tomorrow "
            "our all team member conducting a meeting for our new project"
        )
        self.assertEqual(response.status_code, 200)
        task = Task.objects.get()
        self.assertEqual(task.title, "meeting for new project")
        self.assertEqual(task.priority, Task.Priority.HIGH)

    @patch("tasks.views.interpret", return_value=None)
    def test_same_client_message_is_processed_once(self, _interpret):
        client_id = str(uuid.uuid4())
        payload = {
            "client_message_id": client_id,
            "text": "Add a task with a unique title",
        }
        first = self.client.post("/api/v1/chat/messages/", payload, format="json")
        second = self.client.post("/api/v1/chat/messages/", payload, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.filter(client_message_id=client_id).count(), 1)

    @patch("tasks.views.interpret", return_value=None)
    def test_recent_identical_submission_returns_original_result(self, _interpret):
        text = "Add a task with another unique title"
        first = self.chat(text)
        second = self.chat(text)
        self.assertEqual(Task.objects.count(), 1)
        self.assertIn("Done. I created", first.data["assistant_messages"][0]["text"])
        self.assertIn("Done. I created", second.data["assistant_messages"][0]["text"])
        self.assertNotIn("already exists", second.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_recent_duplicate_content_keeps_creation_success_message(self, _interpret):
        first = self.chat("Add a task with a recent unique title")
        second = self.chat("  Add   a task with a recent unique title  ")
        self.assertIn("Done. I created", first.data["assistant_messages"][0]["text"])
        self.assertIn("Done. I created", second.data["assistant_messages"][0]["text"])
        self.assertEqual(Task.objects.count(), 1)

    @patch("tasks.views.interpret", return_value=None)
    def test_chat_history_survives_history_reload(self, _interpret):
        self.chat("Hello")
        self.chat("Show all tasks")
        history = self.client.get("/api/v1/chat/messages/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data["messages"]), 4)
        self.assertEqual(history.data["messages"][0]["role"], "user")
        self.assertEqual(history.data["messages"][-1]["role"], "assistant")

    @patch("tasks.views.interpret", return_value=None)
    def test_delete_requires_confirmation(self, _interpret):
        task = Task.objects.create(title="Delete me")
        response = self.chat("Delete Delete me")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Task.objects.get(pk=task.pk).deleted_at)
        self.assertEqual(PendingPrompt.objects.count(), 1)
        confirmed = self.chat("yes")
        self.assertEqual(confirmed.status_code, 200)
        self.assertIsNotNone(Task.objects.get(pk=task.pk).deleted_at)

    @patch("tasks.views.interpret", return_value=None)
    def test_exact_delete_prompts_for_confirmation(self, _interpret):
        task = Task.objects.create(title="Review the API")
        response = self.chat('Delete the "review the API" task')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pending_prompt"]["kind"], "confirmation")
        self.assertIsNone(Task.objects.get(pk=task.pk).deleted_at)

    @patch("tasks.views.interpret", return_value=None)
    def test_ambiguous_delete_selects_multiple_then_confirms(self, _interpret):
        first = Task.objects.create(title="Review the API")
        second = Task.objects.create(title="Review the API integration")
        response = self.chat("Delete the API task")
        self.assertEqual(response.data["pending_prompt"]["kind"], "choice")
        selected = self.chat("1 and 2")
        self.assertEqual(selected.data["pending_prompt"]["kind"], "confirmation")
        confirmed = self.chat("yes")
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNotNone(first.deleted_at)
        self.assertIsNotNone(second.deleted_at)
        self.assertIn("Deleted 2 task(s)", confirmed.data["assistant_messages"][0]["text"])

    def test_status_and_edit_validation(self):
        task = Task.objects.create(title="API task")
        status = self.client.post(f"/api/v1/tasks/{task.pk}/status/", {"status": "in_progress"}, format="json")
        self.assertEqual(status.status_code, 200)
        edited = self.client.patch(f"/api/v1/tasks/{task.pk}/", {"priority": "high", "description": "Review"}, format="json")
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.data["priority"], "high")
        invalid = self.client.patch(f"/api/v1/tasks/{task.pk}/", {"title": ""}, format="json")
        self.assertEqual(invalid.status_code, 400)

    @patch("tasks.views.interpret", return_value={"kind": "create", "title": "Validated task", "priority": "urgent"})
    def test_structured_create_rejects_invalid_priority(self, _interpret):
        response = self.chat("Create a validated task")
        self.assertEqual(response.data["assistant_messages"][0]["kind"], "error")
        self.assertIn("Priority must be low, medium, or high", response.data["assistant_messages"][0]["text"])
        self.assertFalse(Task.objects.filter(title="Validated task").exists())

    @patch("tasks.views.interpret", return_value={"kind": "update", "title": "API task", "priority": "urgent"})
    def test_structured_update_rejects_invalid_priority(self, _interpret):
        Task.objects.create(title="API task")
        response = self.chat("Edit the API task priority to urgent")
        self.assertEqual(response.data["assistant_messages"][0]["kind"], "error")
        self.assertIn("Priority must be low, medium, or high", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_edit_description_from_chat(self, _interpret):
        task = Task.objects.create(title="Write deployment guide")
        response = self.chat("Edit the deployment guide task description to include rollback and monitoring instructions")
        task.refresh_from_db()
        self.assertEqual(task.description, "include rollback and monitoring instructions")
        self.assertIn("updated the description", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_set_due_date_from_chat(self, _interpret):
        task = Task.objects.create(title="Review security checklist")
        response = self.chat("Set the due date of the security checklist task to 06-11-2026")
        task.refresh_from_db()
        self.assertEqual(task.due_date.isoformat(), "2026-11-06")
        self.assertIn("2026-11-06", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_remove_due_date_does_not_start_delete_flow(self, _interpret):
        task = Task.objects.create(title="Test notification system", due_date=timezone.localdate())
        response = self.chat("Remove the due date from the notification system task")
        task.refresh_from_db()
        self.assertIsNone(task.due_date)
        self.assertIsNone(task.deleted_at)
        self.assertNotIn("Which task(s) should I delete?", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value={"kind": "status", "title": "Product demo", "status": "in_progress"})
    def test_status_command_reports_the_transition(self, _interpret):
        task = Task.objects.create(title="Prepare the product demo", status=Task.Status.TODO)
        response = self.chat("Move the product demo task to In progress")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.PROGRESS)
        self.assertIn("to In progress", response.data["assistant_messages"][0]["text"])
        self.assertNotIn("already", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value={"kind": "status", "title": "Database", "status": "done"})
    def test_done_command_reports_the_transition(self, _interpret):
        task = Task.objects.create(title="Review the database schema", status=Task.Status.TODO)
        response = self.chat("Mark the database task Done")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)
        self.assertIn("to Done", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value={"kind": "status", "title": "Database", "status": "todo"})
    def test_reopen_command_reports_the_transition(self, _interpret):
        task = Task.objects.create(title="Review the database schema", status=Task.Status.DONE)
        response = self.chat("Reopen the database task")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.TODO)
        self.assertIn("to To do", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_status_commands_are_not_deduplicated_as_create_retries(self, _interpret):
        task = Task.objects.create(title="Review database schema", status=Task.Status.TODO)
        first = self.chat("Move the database schema task to In progress")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.PROGRESS)
        self.assertIn("to In progress", first.data["assistant_messages"][0]["text"])
        second = self.chat("Move the database schema task to In progress")
        self.assertIn("already In progress", second.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_quoted_to_do_status_moves_from_in_progress(self, _interpret):
        task = Task.objects.create(title="Review database schema", status=Task.Status.PROGRESS)
        response = self.chat('Move the database schema task to "to do"')
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.TODO)
        self.assertIn("from In progress to To do", response.data["assistant_messages"][0]["text"])

    @patch("tasks.views.interpret", return_value=None)
    def test_update_status_accepts_hyphenated_in_progress(self, _interpret):
        task = Task.objects.create(title="Review API", status=Task.Status.TODO)
        response = self.chat("Update the status of the review API task to In-progress")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.PROGRESS)
        self.assertIn("from To do to In progress", response.data["assistant_messages"][0]["text"])

    def test_sample_tasks_are_idempotent(self):
        first = self.client.post("/api/v1/tasks/sample/")
        second = self.client.post("/api/v1/tasks/sample/")
        self.assertEqual(first.data["created"], 6)
        self.assertEqual(second.data["created"], 0)

    @patch("tasks.views.interpret", return_value=None)
    def test_fallback_strips_called_from_title(self, _interpret):
        response = self.chat("Create a task called Write project documentation")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Task.objects.filter(title="Write project documentation").exists())

    @patch("tasks.views.interpret", return_value=None)
    def test_numbered_choice_applies_original_status_action(self, _interpret):
        first = Task.objects.create(title="Review API", status=Task.Status.TODO)
        second = Task.objects.create(title="Deploy API", status=Task.Status.TODO)
        response = self.chat("Move the API task to In progress")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["pending_prompt"]["kind"], "choice")
        selected = response.data["pending_prompt"]["action"]["candidate_ids"][0]
        chosen = self.chat("1")
        self.assertEqual(chosen.status_code, 200)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(str(first.pk), selected)
        self.assertEqual(first.status, Task.Status.PROGRESS)
        self.assertEqual(second.status, Task.Status.TODO)

    @patch("tasks.views.interpret", return_value=None)
    def test_search_filters_and_board_filter_are_returned(self, _interpret):
        Task.objects.create(title="Write project documentation", priority=Task.Priority.LOW)
        Task.objects.create(title="Prepare demo", priority=Task.Priority.HIGH)
        high = self.chat("Show high-priority tasks")
        self.assertEqual(high.status_code, 200)
        self.assertEqual(high.data["filter"]["priority"], "high")
        self.assertEqual(high.data["changed_task_ids"], [])
        self.assertEqual(Task.objects.filter(priority=Task.Priority.HIGH).count(), 1)
        low = self.chat("Show me the low priority tasks")
        self.assertEqual(low.status_code, 200)
        self.assertEqual(low.data["filter"]["priority"], "low")
        self.assertEqual(low.data["assistant_messages"][0]["text"], "Found 1 task(s).")
        documentation = self.chat("Find tasks related to documentation")
        self.assertEqual(documentation.status_code, 200)
        self.assertEqual(documentation.data["filter"]["q"], "documentation")

    @patch("tasks.views.interpret", return_value=None)
    def test_semantic_search_matches_api_related_task(self, _interpret):
        Task.objects.create(title="Review API integration", description="Check the backend endpoints")
        response = self.chat("Show me the api related task")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["filter"]["q"], "api")
        self.assertEqual(response.data["assistant_messages"][0]["text"], "Found 1 task(s).")

    @patch("tasks.views.interpret", return_value=None)
    def test_due_date_search_filters_today_and_tomorrow(self, _interpret):
        Task.objects.create(title="Today task", due_date=timezone.localdate())
        Task.objects.create(title="Tomorrow task", due_date=timezone.localdate() + timedelta(days=1))
        today = self.chat("Show me only today's tasks")
        self.assertEqual(today.data["filter"]["due"], "today")
        self.assertEqual(today.data["assistant_messages"][0]["text"], "Found 1 task(s).")
        tomorrow = self.chat("Show me the tasks that I need to do tomorrow")
        self.assertEqual(tomorrow.data["filter"]["due"], "tomorrow")
        self.assertEqual(tomorrow.data["assistant_messages"][0]["text"], "Found 1 task(s).")
        board = self.client.get("/api/v1/tasks/?due=tomorrow")
        self.assertEqual(board.data["count"], 1)
        self.assertEqual(board.data["tasks"][0]["title"], "Tomorrow task")

    @patch("tasks.views.interpret", return_value=None)
    def test_due_tomorrow_phrase_does_not_search_for_due_text(self, _interpret):
        Task.objects.create(title="Tomorrow task", due_date=timezone.localdate() + timedelta(days=1))
        Task.objects.create(title="Another tomorrow task", due_date=timezone.localdate() + timedelta(days=1))
        response = self.chat("Show me all tasks due tomorrow")
        self.assertEqual(response.data["assistant_messages"][0]["text"], "Found 2 task(s).")
        self.assertEqual(response.data["filter"], {"due": "tomorrow"})

    @patch("tasks.views.interpret", return_value=None)
    def test_no_due_date_search_filters_tasks_without_due_date(self, _interpret):
        Task.objects.create(title="Undated task")
        Task.objects.create(title="Dated task", due_date=timezone.localdate())
        response = self.chat("Show me the task which has no due date")
        self.assertEqual(response.data["filter"]["due"], "none")
        self.assertEqual(response.data["assistant_messages"][0]["text"], "Found 1 task(s).")
        board = self.client.get("/api/v1/tasks/?due=none")
        self.assertEqual(board.data["count"], 1)
        self.assertEqual(board.data["tasks"][0]["title"], "Undated task")

    @patch("tasks.views.interpret", return_value=None)
    def test_no_due_date_phrase_does_not_search_for_connector_words(self, _interpret):
        Task.objects.create(title="Undated one")
        Task.objects.create(title="Undated two")
        Task.objects.create(title="Dated task", due_date=timezone.localdate())
        response = self.chat("Show me all tasks which have no due date")
        self.assertEqual(response.data["assistant_messages"][0]["text"], "Found 2 task(s).")
        self.assertEqual(response.data["filter"], {"due": "none"})

    @patch("tasks.views.interpret", return_value=None)
    def test_in_progress_status_search_uses_status_filter(self, _interpret):
        Task.objects.create(title="Active task", status=Task.Status.PROGRESS)
        Task.objects.create(title="Todo task", status=Task.Status.TODO)
        response = self.chat("Show all in progress task")
        self.assertEqual(response.data["assistant_messages"][0]["text"], "Found 1 task(s).")
        self.assertEqual(response.data["filter"], {"status": "progress"})
        board = self.client.get("/api/v1/tasks/?status=progress")
        self.assertEqual(board.data["count"], 1)

    @patch("tasks.views.interpret", return_value=None)
    def test_multiple_numbered_choice_and_misspelled_cancel(self, _interpret):
        Task.objects.create(title="Documentation one")
        Task.objects.create(title="Documentation two")
        response = self.chat("Delete the documentation task")
        self.assertEqual(response.data["pending_prompt"]["kind"], "choice")
        cancelled = self.chat("cencel")
        self.assertEqual(cancelled.status_code, 200)
        self.assertIn("Cancelled", cancelled.data["assistant_messages"][0]["text"])
