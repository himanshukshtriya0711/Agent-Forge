"""
AgentForge Core Module
AI-powered coding assistant with multi-agent architecture
"""

from .llm import GroqClient, GeminiClient, PromptTemplates
from .rag import RAGService, CodeRetriever, VectorStore, CodeChunker
from .tools import FileReader, FileWriter, PatchApplier, Linter, TerminalExecutor
from .agents import (
    Orchestrator,
    PlannerAgent,
    CoderAgent,
    DebugAgent,
    ReviewerAgent,
    ExecutorAgent,
)

__all__ = [
    # LLM
    "GroqClient",
    "GeminiClient",
    "PromptTemplates",
    # RAG
    "RAGService",
    "CodeRetriever",
    "VectorStore",
    "CodeChunker",
    # Tools
    "FileReader",
    "FileWriter",
    "PatchApplier",
    "Linter",
    "TerminalExecutor",
    # Agents
    "Orchestrator",
    "PlannerAgent",
    "CoderAgent",
    "DebugAgent",
    "ReviewerAgent",
    "ExecutorAgent",
]
