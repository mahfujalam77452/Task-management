from rest_framework import serializers
from .models import Task, ChatMessage, PendingPrompt

class TaskSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField()
    due = serializers.DateField(source="due_date", allow_null=True)
    completedAt = serializers.DateTimeField(source="completed_at", allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")
    class Meta:
        model = Task
        fields = ["id", "title", "description", "status", "priority", "due", "createdAt", "completedAt"]

class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "role", "kind", "text", "created_at"]

class PendingPromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingPrompt
        fields = ["id", "kind", "question", "action", "expires_at", "resolved_at", "outcome"]
