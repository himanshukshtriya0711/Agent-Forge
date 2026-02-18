"""
Executor Agent
Executes commands, runs tests, and applies changes
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .base import BaseAgent
from ..llm import PromptTemplates

logger = logging.getLogger("agentforge.agents")


class ExecutorAgent(BaseAgent):
    """
    Executor agent that runs commands, tests, and applies changes
    """

    @property
    def system_prompt(self) -> str:
        return PromptTemplates.EXECUTOR

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task (run command, apply patch, run tests)

        Args:
            task: Task with 'action', 'target', etc.

        Returns:
            Execution results
        """
        action = task.get("action", "").upper()
        
        logger.info(f"ExecutorAgent: Executing {action}")

        if action == "RUN_TEST":
            return self.run_tests(
                test_path=task.get("test_path"),
                verbose=task.get("verbose", True),
            )
        elif action == "RUN_LINT":
            return self.run_lint(
                file_path=task.get("file_path"),
            )
        elif action == "APPLY_PATCH":
            return self.apply_code_patch(
                file_path=task.get("file_path"),
                diff=task.get("diff"),
            )
        elif action == "CREATE_FILE":
            return self.create_new_file(
                file_path=task.get("file_path"),
                content=task.get("content"),
            )
        elif action == "CHECK_SYNTAX":
            return self.check_code_syntax(
                file_path=task.get("file_path"),
                content=task.get("content"),
            )
        elif action == "RUN_COMMAND":
            return self.run_safe_command(
                command=task.get("command"),
                timeout=task.get("timeout", 30),
            )
        else:
            return {
                "success": False,
                "error": f"Unknown action: {action}",
            }

    def run_tests(
        self,
        test_path: Optional[str] = None,
        verbose: bool = True,
        timeout: int = 120,
    ) -> Dict[str, Any]:
        """
        Run pytest tests

        Args:
            test_path: Specific test file or directory
            verbose: Enable verbose output
            timeout: Test timeout

        Returns:
            Test results
        """
        if not self.terminal:
            return {
                "success": False,
                "error": "Terminal not available",
            }

        result = self.terminal.run_tests(
            test_path=test_path,
            verbose=verbose,
            timeout=timeout,
        )

        return {
            "success": result.get("success", False),
            "action": "RUN_TEST",
            "test_path": test_path or "all tests",
            "output": result.get("stdout", ""),
            "errors": result.get("stderr", ""),
            "test_summary": result.get("test_summary", {}),
        }

    def run_lint(
        self,
        file_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run flake8 linting

        Args:
            file_path: Specific file or project-wide

        Returns:
            Lint results
        """
        if file_path:
            result = self.lint_file(file_path)
        elif self.linter:
            result = self.linter.lint_project()
        else:
            return {
                "success": False,
                "error": "Linter not available",
            }

        return {
            "success": result.get("success", False),
            "action": "RUN_LINT",
            "target": file_path or "project",
            "issues": result.get("issues", []),
            "issue_count": result.get("issue_count", 0),
            "has_errors": result.get("has_errors", False),
        }

    def apply_code_patch(
        self,
        file_path: str,
        diff: str,
        validate: bool = True,
    ) -> Dict[str, Any]:
        """
        Apply a diff patch to a file

        Args:
            file_path: Target file
            diff: Unified diff
            validate: Run linter after applying

        Returns:
            Application results
        """
        if not self.patch_applier:
            return {
                "success": False,
                "error": "Patch applier not available",
            }

        # Apply the patch
        result = self.apply_patch(file_path, diff)

        if not result.get("success"):
            return {
                "success": False,
                "action": "APPLY_PATCH",
                "file_path": file_path,
                "error": result.get("error", "Failed to apply patch"),
            }

        # Validate with linter if requested
        validation_result = None
        if validate and file_path.endswith(".py"):
            validation_result = self.lint_file(file_path)

        return {
            "success": True,
            "action": "APPLY_PATCH",
            "file_path": file_path,
            "lines_added": result.get("lines_added", 0),
            "lines_removed": result.get("lines_removed", 0),
            "backup_path": result.get("backup_path"),
            "validation": validation_result,
        }

    def create_new_file(
        self,
        file_path: str,
        content: str,
        validate: bool = True,
    ) -> Dict[str, Any]:
        """
        Create a new file

        Args:
            file_path: Path for new file
            content: File content
            validate: Validate syntax before creating

        Returns:
            Creation results
        """
        if not self.file_writer:
            return {
                "success": False,
                "error": "File writer not available",
            }

        # Validate syntax first if Python
        if validate and file_path.endswith(".py"):
            syntax_check = self.check_syntax(content)
            if not syntax_check.get("valid", False):
                return {
                    "success": False,
                    "action": "CREATE_FILE",
                    "file_path": file_path,
                    "error": "Syntax validation failed",
                    "syntax_error": syntax_check.get("error"),
                }

        # Create the file
        result = self.file_writer.create_file(file_path, content)

        if not result.get("success"):
            # Try write_file instead (it handles existing files)
            result = self.write_file(file_path, content)

        return {
            "success": result.get("success", False),
            "action": "CREATE_FILE",
            "file_path": file_path,
            "size": result.get("size"),
            "error": result.get("error"),
        }

    def check_code_syntax(
        self,
        file_path: Optional[str] = None,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Check code syntax

        Args:
            file_path: File to check
            content: Or content to check directly

        Returns:
            Syntax check results
        """
        if content:
            result = self.check_syntax(content)
        elif file_path and self.linter:
            result = self.linter.check_file_syntax(file_path)
        else:
            return {
                "success": False,
                "error": "No content or file path provided",
            }

        return {
            "success": result.get("success", False),
            "action": "CHECK_SYNTAX",
            "valid": result.get("valid", False),
            "error": result.get("error"),
        }

    def run_safe_command(
        self,
        command: str,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        Run a command after safety validation

        Args:
            command: Command to run
            timeout: Execution timeout

        Returns:
            Command results
        """
        if not self.terminal:
            return {
                "success": False,
                "error": "Terminal not available",
            }

        # Check safety first
        safety_check = self.terminal.is_command_safe(command)
        if not safety_check.get("safe"):
            return {
                "success": False,
                "action": "RUN_COMMAND",
                "command": command,
                "blocked": True,
                "reason": safety_check.get("reason"),
            }

        # Execute
        result = self.run_command(command, timeout)

        return {
            "success": result.get("success", False),
            "action": "RUN_COMMAND",
            "command": command,
            "exit_code": result.get("exit_code"),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "timed_out": result.get("timed_out", False),
        }

    def rollback_file(
        self,
        file_path: str,
        backup_name: str,
    ) -> Dict[str, Any]:
        """
        Rollback a file to a backup

        Args:
            file_path: Target file path
            backup_name: Name of backup to restore

        Returns:
            Rollback results
        """
        if not self.file_writer:
            return {
                "success": False,
                "error": "File writer not available",
            }

        result = self.file_writer.restore_backup(backup_name, file_path)

        return {
            "success": result.get("success", False),
            "action": "ROLLBACK",
            "file_path": file_path,
            "restored_from": result.get("restored_from"),
            "error": result.get("error"),
        }

    def list_backups(self) -> Dict[str, Any]:
        """
        List available backups

        Returns:
            List of backups
        """
        if not self.file_writer:
            return {
                "success": False,
                "error": "File writer not available",
            }

        return self.file_writer.list_backups()
