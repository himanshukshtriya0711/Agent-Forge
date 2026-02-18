"""
IDE Views
Django views for the AgentForge IDE
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpRequest, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings

from .models import Project, ChatSession, ChatMessage, PendingChange
from core import Orchestrator, RAGService, FileReader, FileWriter, PatchApplier, TerminalExecutor

logger = logging.getLogger("agentforge.ide")


# =============================================================================
# Page Views
# =============================================================================

def home(request: HttpRequest) -> HttpResponse:
    """Render the hero/landing page"""
    return render(request, "ide/home.html")


def dashboard(request: HttpRequest) -> HttpResponse:
    """Render the project dashboard"""
    projects = Project.objects.all()
    return render(request, "ide/dashboard.html", {"projects": projects})


def editor(request: HttpRequest, project_id: str) -> HttpResponse:
    """Render the IDE editor for a project"""
    project = get_object_or_404(Project, id=project_id)
    
    # Get most recent session or create a new one
    session = ChatSession.objects.filter(project=project).order_by('-created_at').first()
    if not session:
        session = ChatSession.objects.create(project=project)
    
    # Get recent messages
    messages = session.messages.all()[:50]
    
    # Get pending changes
    pending_changes = session.pending_changes.filter(status="pending")
    
    return render(request, "ide/editor.html", {
        "project": project,
        "session": session,
        "messages": messages,
        "pending_changes": pending_changes,
    })


# =============================================================================
# Project API Endpoints
# =============================================================================

@require_http_methods(["POST"])
def create_project(request: HttpRequest) -> JsonResponse:
    """Create a new project"""
    try:
        data = json.loads(request.body)
        name = data.get("name", "").strip()
        description = data.get("description", "")
        
        if not name:
            return JsonResponse({"error": "Project name is required"}, status=400)
        
        # Create project directory
        project_dir = settings.PROJECTS_DIR / name.replace(" ", "_").lower()
        project_dir.mkdir(parents=True, exist_ok=True)
        
        # Create project record
        project = Project.objects.create(
            name=name,
            description=description,
            path=str(project_dir),
        )
        
        logger.info(f"Created project: {name}")
        
        return JsonResponse({
            "success": True,
            "project": {
                "id": str(project.id),
                "name": project.name,
                "path": project.path,
            }
        })
        
    except Exception as e:
        logger.error(f"Error creating project: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["DELETE"])
def delete_project(request: HttpRequest, project_id: str) -> JsonResponse:
    """Delete a project"""
    try:
        project = get_object_or_404(Project, id=project_id)
        project.delete()
        
        return JsonResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error deleting project: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["POST"])
def index_project(request: HttpRequest, project_id: str) -> JsonResponse:
    """Index a project for RAG"""
    try:
        project = get_object_or_404(Project, id=project_id)
        
        rag = RAGService(project_path=Path(project.path))
        result = rag.index_project(force_reindex=True)
        
        if result["success"]:
            project.is_indexed = True
            project.index_count = result.get("document_count", 0)
            project.save()
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error indexing project: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# File System API Endpoints
# =============================================================================

@require_http_methods(["GET"])
def get_file_tree(request: HttpRequest, project_id: str) -> JsonResponse:
    """Get the file tree for a project"""
    try:
        project = get_object_or_404(Project, id=project_id)
        reader = FileReader(Path(project.path))
        
        result = reader.list_directory(".", recursive=True)
        
        if result["success"]:
            # Build tree structure
            tree = _build_file_tree(result["contents"])
            return JsonResponse({"success": True, "tree": tree})
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error getting file tree: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def _build_file_tree(contents: list) -> list:
    """Build a hierarchical tree structure from flat file list"""
    tree = {}
    
    for item in contents:
        path_parts = Path(item["path"]).parts
        current = tree
        
        for i, part in enumerate(path_parts):
            if part not in current:
                is_last = i == len(path_parts) - 1
                current[part] = {
                    "name": part,
                    "path": str(Path(*path_parts[:i+1])),
                    "is_file": is_last and item["is_file"],
                    "is_dir": is_last and item["is_dir"],
                    "children": {} if not (is_last and item["is_file"]) else None,
                }
            if current[part]["children"] is not None:
                current = current[part]["children"]
    
    def tree_to_list(node: dict) -> list:
        result = []
        for key, value in sorted(node.items(), key=lambda x: (x[1].get("is_file", False), x[0])):
            item = {
                "name": value["name"],
                "path": value["path"],
                "is_file": value.get("is_file", False),
                "is_dir": value.get("is_dir", False),
            }
            if value.get("children"):
                item["children"] = tree_to_list(value["children"])
            result.append(item)
        return result
    
    return tree_to_list(tree)


@require_http_methods(["GET"])
def get_file_content(request: HttpRequest, project_id: str) -> JsonResponse:
    """Get the content of a file"""
    try:
        project = get_object_or_404(Project, id=project_id)
        file_path = request.GET.get("path", "")
        
        if not file_path:
            return JsonResponse({"error": "File path required"}, status=400)
        
        reader = FileReader(Path(project.path))
        result = reader.read_file(file_path)
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error reading file: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["POST"])
def save_file(request: HttpRequest, project_id: str) -> JsonResponse:
    """Save file content"""
    try:
        project = get_object_or_404(Project, id=project_id)
        data = json.loads(request.body)
        file_path = data.get("path", "")
        content = data.get("content", "")
        
        if not file_path:
            return JsonResponse({"error": "File path required"}, status=400)
        
        writer = FileWriter(Path(project.path))
        result = writer.write_file(file_path, content)
        
        # Re-index the file
        if result["success"]:
            try:
                rag = RAGService(project_path=Path(project.path))
                rag.index_file(file_path, content)
            except Exception as e:
                logger.warning(f"Failed to re-index file: {e}")
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["POST"])
def create_file(request: HttpRequest, project_id: str) -> JsonResponse:
    """Create a new file"""
    try:
        project = get_object_or_404(Project, id=project_id)
        data = json.loads(request.body)
        file_path = data.get("path", "")
        content = data.get("content", "")
        
        if not file_path:
            return JsonResponse({"error": "File path required"}, status=400)
        
        writer = FileWriter(Path(project.path))
        result = writer.create_file(file_path, content)
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error creating file: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def run_file(request: HttpRequest, project_id: str) -> JsonResponse:
    """Run/execute a file"""
    try:
        project = get_object_or_404(Project, id=project_id)
        data = json.loads(request.body)
        file_path = data.get("path", "")
        
        if not file_path:
            return JsonResponse({"error": "File path required"}, status=400)
        
        # Get file extension to determine how to run
        ext = Path(file_path).suffix.lower()
        
        terminal = TerminalExecutor(Path(project.path))
        
        # Determine command based on file type
        if ext == ".py":
            command = f"python {file_path}"
        elif ext == ".js":
            command = f"node {file_path}"
        elif ext == ".ts":
            command = f"npx ts-node {file_path}"
        elif ext == ".sh":
            command = f"bash {file_path}"
        elif ext == ".ps1":
            command = f"powershell -File {file_path}"
        elif ext in [".html", ".htm"]:
            # For HTML files, return the file path for browser preview
            full_path = Path(project.path) / file_path
            return JsonResponse({
                "success": True,
                "type": "html_preview",
                "file_path": str(full_path),
                "message": "HTML file ready for preview",
            })
        elif ext in [".css", ".json", ".md", ".txt"]:
            return JsonResponse({
                "success": False,
                "error": f".{ext[1:]} files are not executable. They are data/config files."
            })
        else:
            return JsonResponse({
                "success": False,
                "error": f"Don't know how to run .{ext} files. Supported: .py, .js, .ts, .html"
            })
        
        result = terminal.execute(command, timeout=30)
        
        return JsonResponse({
            "success": result.get("success", False),
            "command": command,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", -1),
        })
        
    except Exception as e:
        logger.error(f"Error running file: {e}")
        return JsonResponse({"error": str(e)}, status=500)


# =============================================================================
# Agent Chat API Endpoints
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def chat(request: HttpRequest, project_id: str) -> JsonResponse:
    """Process a chat message through the agent system"""
    try:
        project = get_object_or_404(Project, id=project_id)
        data = json.loads(request.body)
        message = data.get("message", "").strip()
        session_id = data.get("session_id")
        
        if not message:
            return JsonResponse({"error": "Message required"}, status=400)
        
        # Get or create session
        if session_id:
            session = get_object_or_404(ChatSession, id=session_id, project=project)
        else:
            session = ChatSession.objects.create(project=project)
        
        # Save user message
        ChatMessage.objects.create(
            session=session,
            role="user",
            content=message,
        )
        
        # Get chat history
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in session.messages.all()[:20]
        ]
        
        # Process through orchestrator
        orchestrator = Orchestrator(
            project_path=Path(project.path),
            auto_apply=False,  # Always require user approval
        )
        
        result = orchestrator.process_request(message)
        
        # Save assistant response
        response_content = _format_response(result)
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=response_content,
            metadata=result,
        )
        
        # Create pending changes if any
        pending_changes = []
        if result.get("success") and result.get("final_result"):
            for change in result["final_result"].get("changes", []):
                pending = PendingChange.objects.create(
                    session=session,
                    change_type=change.get("type", "modify"),
                    file_path=change.get("file", ""),
                    new_content=change.get("content", ""),
                    diff=change.get("diff", ""),
                    explanation=change.get("explanation", ""),
                )
                pending_changes.append({
                    "id": str(pending.id),
                    "type": pending.change_type,
                    "file": pending.file_path,
                    "diff": pending.diff,
                })
        
        return JsonResponse({
            "success": True,
            "session_id": str(session.id),
            "response": response_content,
            "pending_changes": pending_changes,
            "result": result,
        })
        
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def _format_response(result: Dict[str, Any]) -> str:
    """Format orchestrator result as user-friendly response"""
    if result.get("response"):
        return result["response"]
    
    if not result.get("success"):
        return f"Sorry, I encountered an error: {result.get('error', 'Unknown error')}"
    
    parts = []
    
    if result.get("plan"):
        parts.append(f"**Plan:** {result['plan'].get('plan_summary', 'Created plan')}")
    
    final = result.get("final_result", {})
    
    if final.get("changes"):
        parts.append(f"\n**Changes:** {len(final['changes'])} file(s) to modify")
        for change in final["changes"]:
            parts.append(f"- `{change.get('file', 'Unknown')}`")
    
    if final.get("suggestions"):
        parts.append("\n**Suggestions:**")
        for suggestion in final["suggestions"][:3]:
            parts.append(f"- {suggestion}")
    
    return "\n".join(parts) if parts else "Done!"


# =============================================================================
# Change Management API Endpoints
# =============================================================================

@csrf_exempt
@require_http_methods(["POST"])
def apply_change(request: HttpRequest, project_id: str, change_id: str) -> JsonResponse:
    """Apply a pending change"""
    try:
        project = get_object_or_404(Project, id=project_id)
        change = get_object_or_404(PendingChange, id=change_id)
        
        if change.status != "pending":
            return JsonResponse({"error": "Change already processed"}, status=400)
        
        # Apply the change
        if change.change_type == "create":
            writer = FileWriter(Path(project.path))
            result = writer.write_file(change.file_path, change.new_content)
        elif change.diff:
            applier = PatchApplier(Path(project.path))
            result = applier.apply_patch(change.file_path, change.diff)
        else:
            writer = FileWriter(Path(project.path))
            result = writer.write_file(change.file_path, change.new_content)
        
        if result.get("success"):
            change.status = "applied"
            change.applied_at = timezone.now()
            change.save()
            
            # Re-index the file
            try:
                rag = RAGService(project_path=Path(project.path))
                reader = FileReader(Path(project.path))
                file_result = reader.read_file(change.file_path)
                if file_result["success"]:
                    rag.index_file(change.file_path, file_result["content"])
            except Exception as e:
                logger.warning(f"Failed to re-index: {e}")
            
            return JsonResponse({"success": True})
        
        return JsonResponse({"success": False, "error": result.get("error")})
        
    except Exception as e:
        logger.error(f"Error applying change: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def reject_change(request: HttpRequest, project_id: str, change_id: str) -> JsonResponse:
    """Reject a pending change"""
    try:
        change = get_object_or_404(PendingChange, id=change_id)
        
        change.status = "rejected"
        change.save()
        
        return JsonResponse({"success": True})
        
    except Exception as e:
        logger.error(f"Error rejecting change: {e}")
        return JsonResponse({"error": str(e)}, status=500)


@require_http_methods(["GET"])
def preview_change(request: HttpRequest, project_id: str, change_id: str) -> JsonResponse:
    """Preview a pending change"""
    try:
        project = get_object_or_404(Project, id=project_id)
        change = get_object_or_404(PendingChange, id=change_id)
        
        # Get original content
        reader = FileReader(Path(project.path))
        original = reader.read_file(change.file_path)
        
        # Get preview of patched content
        if change.diff:
            applier = PatchApplier(Path(project.path))
            preview = applier.preview_patch(change.file_path, change.diff)
            new_content = preview.get("patched_content", change.new_content)
        else:
            new_content = change.new_content
        
        return JsonResponse({
            "success": True,
            "original": original.get("content", ""),
            "new": new_content,
            "diff": change.diff,
            "file_path": change.file_path,
        })
        
    except Exception as e:
        logger.error(f"Error previewing change: {e}")
        return JsonResponse({"error": str(e)}, status=500)

