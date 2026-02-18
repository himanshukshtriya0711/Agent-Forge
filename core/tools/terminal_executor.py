"""
Terminal Executor Tool
Provides restricted terminal execution for safe command running
"""

import os
import re
import subprocess
import shlex
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
from django.conf import settings

logger = logging.getLogger("agentforge.tools")


class TerminalExecutor:
    """
    Restricted terminal executor that only allows safe commands
    Prevents arbitrary shell execution and dangerous operations
    """

    # Allowed commands (whitelist)
    ALLOWED_COMMANDS: Set[str] = {
        "python",
        "pip",
        "pytest",
        "flake8",
        "mypy",
        "black",
        "isort",
        "ls",
        "dir",
        "cat",
        "type",
        "echo",
        "pwd",
        "cd",
        "find",
        "grep",
        "head",
        "tail",
        "wc",
    }

    # Allowed pip subcommands
    ALLOWED_PIP_COMMANDS: Set[str] = {
        "list",
        "show",
        "freeze",
        "check",
    }

    # Allowed python flags
    ALLOWED_PYTHON_FLAGS: Set[str] = {
        "-m",
        "-c",
        "--version",
        "-V",
    }

    # Dangerous patterns to block
    DANGEROUS_PATTERNS: List[str] = [
        r"\brm\b",
        r"\bdel\b",
        r"\brmdir\b",
        r"\brd\b",
        r"\bformat\b",
        r"\bsudo\b",
        r"\badmin\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\bkill\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bcurl\b(?!.*localhost)",
        r"\bwget\b(?!.*localhost)",
        r"\bnc\b",
        r"\bnetcat\b",
        r"\bssh\b",
        r"\btelnet\b",
        r"\bftp\b",
        r">\s*/dev",
        r"\|\s*sh\b",
        r"\|\s*bash\b",
        r"\|\s*cmd\b",
        r"\|\s*powershell\b",
        r"`[^`]+`",  # Command substitution
        r"\$\([^)]+\)",  # Command substitution
        r"&&\s*(rm|del|sudo)",
        r";\s*(rm|del|sudo)",
    ]

    # Maximum execution time (seconds)
    DEFAULT_TIMEOUT = 60
    MAX_TIMEOUT = 300

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize TerminalExecutor

        Args:
            project_path: Root path of the project (working directory)
        """
        self.project_path = Path(project_path) if project_path else settings.PROJECTS_DIR
        self.project_path = self.project_path.resolve()

    def is_command_safe(self, command: str) -> Dict[str, Any]:
        """
        Check if a command is safe to execute

        Args:
            command: The command to check

        Returns:
            Dictionary with safety check results
        """
        command = command.strip()

        # Check for dangerous patterns
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return {
                    "safe": False,
                    "reason": f"Command matches dangerous pattern: {pattern}",
                }

        # Parse command
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return {
                "safe": False,
                "reason": f"Invalid command syntax: {e}",
            }

        if not parts:
            return {
                "safe": False,
                "reason": "Empty command",
            }

        base_command = parts[0].lower()

        # Check if base command is allowed
        # Handle path-qualified commands
        base_name = os.path.basename(base_command)
        if base_name.endswith(".exe"):
            base_name = base_name[:-4]

        if base_name not in self.ALLOWED_COMMANDS:
            return {
                "safe": False,
                "reason": f"Command '{base_name}' is not in the allowed list",
            }

        # Additional checks for specific commands
        if base_name == "pip" and len(parts) > 1:
            if parts[1] not in self.ALLOWED_PIP_COMMANDS:
                if parts[1] not in {"install", "uninstall"}:
                    return {
                        "safe": False,
                        "reason": f"pip subcommand '{parts[1]}' requires manual approval",
                    }

        if base_name == "python" and len(parts) > 1:
            if parts[1] == "-c":
                # Allow simple syntax checks
                code = " ".join(parts[2:]) if len(parts) > 2 else ""
                if "import os" in code or "subprocess" in code or "eval" in code:
                    return {
                        "safe": False,
                        "reason": "Python -c with potentially dangerous imports",
                    }

        return {
            "safe": True,
            "reason": "Command passed safety checks",
        }

    def execute(
        self,
        command: str,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        force_unsafe: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a command safely

        Args:
            command: The command to execute
            timeout: Execution timeout in seconds
            env: Additional environment variables
            force_unsafe: Skip safety checks (use with caution)

        Returns:
            Dictionary with execution results
        """
        command = command.strip()

        # Safety check
        if not force_unsafe:
            safety = self.is_command_safe(command)
            if not safety["safe"]:
                logger.warning(f"Blocked unsafe command: {command}")
                return {
                    "success": False,
                    "error": f"Command blocked: {safety['reason']}",
                    "blocked": True,
                }

        # Set timeout
        timeout = min(timeout or self.DEFAULT_TIMEOUT, self.MAX_TIMEOUT)

        # Prepare environment
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        try:
            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.project_path),
                env=exec_env,
            )

            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command,
                "timed_out": False,
            }

        except subprocess.TimeoutExpired as e:
            return {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
                "command": command,
                "timed_out": True,
                "partial_stdout": e.stdout if e.stdout else "",
                "partial_stderr": e.stderr if e.stderr else "",
            }
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return {
                "success": False,
                "error": str(e),
                "command": command,
            }

    def run_python_module(
        self,
        module: str,
        args: Optional[List[str]] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Run a Python module with -m flag

        Args:
            module: Module name (e.g., 'pytest', 'flake8')
            args: Additional arguments
            timeout: Execution timeout

        Returns:
            Dictionary with execution results
        """
        # Allowed modules
        allowed_modules = {"pytest", "flake8", "mypy", "black", "isort", "pip", "ast"}
        
        if module not in allowed_modules:
            return {
                "success": False,
                "error": f"Module '{module}' is not allowed",
            }

        cmd_parts = ["python", "-m", module]
        if args:
            cmd_parts.extend(args)

        command = shlex.join(cmd_parts)
        return self.execute(command, timeout=timeout, force_unsafe=True)

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
            Dictionary with test results
        """
        args = []
        if verbose:
            args.append("-v")
        if test_path:
            args.append(test_path)

        result = self.run_python_module("pytest", args, timeout=timeout)

        # Parse test results if successful
        if result.get("stdout"):
            result["test_summary"] = self._parse_pytest_output(result["stdout"])

        return result

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """Parse pytest output for summary"""
        import re

        summary = {
            "passed": 0,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
        }

        # Look for summary line like "5 passed, 2 failed"
        patterns = [
            (r"(\d+) passed", "passed"),
            (r"(\d+) failed", "failed"),
            (r"(\d+) error", "errors"),
            (r"(\d+) skipped", "skipped"),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, output)
            if match:
                summary[key] = int(match.group(1))

        return summary

    def check_syntax(self, file_path: str) -> Dict[str, Any]:
        """
        Check Python syntax using ast module

        Args:
            file_path: Path to Python file

        Returns:
            Dictionary with syntax check results
        """
        # Read file and check syntax
        try:
            full_path = self.project_path / file_path
            if not full_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                }

            command = f'python -c "import ast; ast.parse(open(r\'{full_path}\').read())"'
            return self.execute(command, timeout=10, force_unsafe=True)

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def get_python_version(self) -> Dict[str, Any]:
        """Get Python version information"""
        return self.execute("python --version", timeout=10)

    def pip_list(self) -> Dict[str, Any]:
        """List installed packages"""
        return self.run_python_module("pip", ["list"], timeout=30)
