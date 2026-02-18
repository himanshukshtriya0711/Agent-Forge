"""
IDE Models
Database models for projects and sessions
"""

from django.db import models
from django.utils import timezone
import uuid


class Project(models.Model):
    """Represents a user project"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    path = models.CharField(max_length=1024, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_indexed = models.BooleanField(default=False)
    index_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name


class ChatSession(models.Model):
    """Represents a chat session with the AI agent"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="chat_sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class ChatMessage(models.Model):
    """Represents a single message in a chat session"""

    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class PendingChange(models.Model):
    """Represents a pending code change awaiting approval"""

    CHANGE_TYPE_CHOICES = [
        ("create", "Create File"),
        ("modify", "Modify File"),
        ("delete", "Delete File"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("applied", "Applied"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="pending_changes"
    )
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES)
    file_path = models.CharField(max_length=1024)
    original_content = models.TextField(blank=True)
    new_content = models.TextField(blank=True)
    diff = models.TextField(blank=True)
    explanation = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

