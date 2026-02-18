"""
Core LLM Module for AgentForge
Provides unified interface for Groq LLM (Llama models)
"""

from .client import GroqClient, GeminiClient  # GeminiClient is alias for backward compat
from .prompts import PromptTemplates

__all__ = ["GroqClient", "GeminiClient", "PromptTemplates"]
