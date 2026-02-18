"""
Base Agent with AutoGen + Groq Integration
Abstract base class for all agents in the multi-agent system
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pathlib import Path

from ..llm import GroqClient
from ..tools import FileReader, FileWriter, PatchApplier, Linter, TerminalExecutor

logger = logging.getLogger("agentforge.agents")


class BaseAgent(ABC):
    """
    Abstract base class for agents
    Provides common functionality and interface for all agents
    Uses Groq LLM backend
    """

    def __init__(
        self,
        project_path: Optional[Path] = None,
        llm_client: Optional[GroqClient] = None,
    ):
        """
        Initialize base agent

        Args:
            project_path: Path to the project
            llm_client: LLM client instance
        """
        self.project_path = Path(project_path) if project_path else None
        self.llm = llm_client or GroqClient()
        
        # RAG disabled for now
        self.rag = None

        # Initialize tools
        if self.project_path:
            self.file_reader = FileReader(self.project_path)
            self.file_writer = FileWriter(self.project_path)
            self.patch_applier = PatchApplier(self.project_path)
            self.linter = Linter(self.project_path)
            self.terminal = TerminalExecutor(self.project_path)
        else:
            self.file_reader = None
            self.file_writer = None
            self.patch_applier = None
            self.linter = None
            self.terminal = None

        self.name = self.__class__.__name__
        self.chat_history: List[Dict[str, str]] = []

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent"""
        pass

    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's main task

        Args:
            task: Task specification dictionary

        Returns:
            Result dictionary
        """
        pass

    def think(
        self,
        user_message: str,
        context: Optional[str] = None,
        return_json: bool = True,
    ) -> Dict[str, Any]:
        """
        Process a message through the LLM

        Args:
            user_message: The message to process
            context: Optional additional context
            return_json: Whether to parse response as JSON

        Returns:
            LLM response (parsed as JSON if requested)
        """
        # Build full prompt with context
        full_message = user_message
        if context:
            full_message = f"{context}\n\n---\n\n{user_message}"

        logger.debug(f"{self.name}: Processing message")

        try:
            if return_json:
                response = self.llm.chat_json(
                    user_message=full_message,
                    system_prompt=self.system_prompt,
                    chat_history=self.chat_history,
                )
            else:
                response = self.llm.chat(
                    user_message=full_message,
                    system_prompt=self.system_prompt,
                    chat_history=self.chat_history,
                )
                response = {"response": response}

            # Update chat history
            self.chat_history.append({"role": "user", "content": full_message})
            self.chat_history.append({
                "role": "assistant",
                "content": str(response),
            })

            return response

        except Exception as e:
            logger.error(f"{self.name}: Error in think: {e}")
            return {"error": str(e)}

    def get_code_context(
        self,
        query: str,
        top_k: int = 5,
    ) -> str:
        """
        Get relevant code context from RAG

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            Formatted code context
        """
        if not self.rag:
            return "No RAG service available"

        return self.rag.get_context(query, top_k)

    def read_file(self, file_path: str) -> Dict[str, Any]:
        """Read a file from the project"""
        if not self.file_reader:
            return {"success": False, "error": "No file reader available"}
        return self.file_reader.read_file(file_path)

    def write_file(self, file_path: str, content: str) -> Dict[str, Any]:
        """Write content to a file"""
        if not self.file_writer:
            return {"success": False, "error": "No file writer available"}
        return self.file_writer.write_file(file_path, content)

    def apply_patch(self, file_path: str, diff: str) -> Dict[str, Any]:
        """Apply a diff patch to a file"""
        if not self.patch_applier:
            return {"success": False, "error": "No patch applier available"}
        return self.patch_applier.apply_patch(file_path, diff)

    def lint_file(self, file_path: str) -> Dict[str, Any]:
        """Lint a file"""
        if not self.linter:
            return {"success": False, "error": "No linter available"}
        return self.linter.lint_file(file_path)

    def lint_content(self, content: str) -> Dict[str, Any]:
        """Lint code content"""
        if not self.linter:
            return {"success": False, "error": "No linter available"}
        return self.linter.lint_content(content)

    def check_syntax(self, content: str) -> Dict[str, Any]:
        """Check Python syntax"""
        if not self.linter:
            return {"success": False, "error": "No linter available"}
        return self.linter.check_syntax(content)

    def run_command(self, command: str, timeout: int = 30) -> Dict[str, Any]:
        """Run a terminal command"""
        if not self.terminal:
            return {"success": False, "error": "No terminal available"}
        return self.terminal.execute(command, timeout=timeout)

    def clear_history(self):
        """Clear chat history"""
        self.chat_history = []

    def get_project_structure(self) -> str:
        """Get the project structure"""
        if not self.file_reader:
            return "No file reader available"
        return self.file_reader.get_project_structure()

    def to_dict(self) -> Dict[str, Any]:
        """Serialize agent state"""
        return {
            "name": self.name,
            "project_path": str(self.project_path) if self.project_path else None,
            "history_length": len(self.chat_history),
        }
