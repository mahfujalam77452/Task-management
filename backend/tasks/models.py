import uuid
from django.db import models
from django.utils import timezone

class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "To do"
        PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, max_length=1000)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.LOW)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_message_id = models.UUIDField(null=True, blank=True, unique=True)
    role = models.CharField(max_length=10)
    kind = models.CharField(max_length=20, default="success")
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

class PendingPrompt(models.Model):
    class Kind(models.TextChoices):
        CONFIRM = "confirmation", "Confirmation"
        CHOICE = "choice", "Choice"
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    question = models.TextField()
    action = models.JSONField()
    expires_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def active(self):
        return self.resolved_at is None and self.expires_at > timezone.now()
