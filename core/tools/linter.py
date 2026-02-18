"""
Linter Tool
Provides code linting and validation using flake8
"""

import os
import ast
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from django.conf import settings

logger = logging.getLogger("agentforge.tools")


class Linter:
    """
    Code linter using flake8 for Python files
    Also provides syntax validation
    """

    # Flake8 error codes to ignore (can be customized)
    DEFAULT_IGNORE = ["E501", "W503"]  # Line too long, line break before binary operator

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize Linter

        Args:
            project_path: Root path of the project
        """
        self.project_path = Path(project_path) if project_path else settings.PROJECTS_DIR
        self.project_path = self.project_path.resolve()

    def _validate_path(self, file_path: str) -> Path:
        """Validate file path is within project"""
        path = Path(file_path)
        if not path.is_absolute():
            path = self.project_path / path
        path = path.resolve()

        try:
            path.relative_to(self.project_path)
        except ValueError:
            raise ValueError(f"Access denied: Path {file_path} is outside project workspace")

        return path

    def lint_file(
        self,
        file_path: str,
        ignore_codes: Optional[List[str]] = None,
        max_line_length: int = 120,
    ) -> Dict[str, Any]:
        """
        Lint a file using flake8

        Args:
            file_path: Path to the file to lint
            ignore_codes: Error codes to ignore
            max_line_length: Maximum line length

        Returns:
            Dictionary with lint results
        """
        try:
            target_path = self._validate_path(file_path)

            if not target_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                }

            if not target_path.suffix == ".py":
                return {
                    "success": True,
                    "message": "Linting only supported for Python files",
                    "issues": [],
                }

            # Build flake8 command
            ignore = ignore_codes or self.DEFAULT_IGNORE
            cmd = [
                "python", "-m", "flake8",
                str(target_path),
                f"--max-line-length={max_line_length}",
                f"--ignore={','.join(ignore)}",
                "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
            ]

            # Run flake8
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(self.project_path),
            )

            # Parse output
            issues = []
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parsed = self._parse_flake8_line(line)
                        if parsed:
                            issues.append(parsed)

            return {
                "success": True,
                "file": str(target_path.relative_to(self.project_path)),
                "issues": issues,
                "issue_count": len(issues),
                "has_errors": len(issues) > 0,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Linting timed out",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "error": "flake8 not installed. Run: pip install flake8",
            }
        except Exception as e:
            logger.error(f"Error linting file: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _parse_flake8_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single flake8 output line"""
        import re
        
        # Pattern: path:line:col: code message
        pattern = r"(.+?):(\d+):(\d+): ([A-Z]\d+) (.+)"
        match = re.match(pattern, line)
        
        if match:
            return {
                "file": match.group(1),
                "line": int(match.group(2)),
                "column": int(match.group(3)),
                "code": match.group(4),
                "message": match.group(5),
                "severity": self._get_severity(match.group(4)),
            }
        return None

    def _get_severity(self, code: str) -> str:
        """Determine severity from flake8 code"""
        if code.startswith("E"):
            return "error"
        elif code.startswith("W"):
            return "warning"
        elif code.startswith("F"):
            return "error"  # Fatal/import errors
        elif code.startswith("C"):
            return "convention"
        else:
            return "info"

    def lint_content(
        self,
        content: str,
        ignore_codes: Optional[List[str]] = None,
        max_line_length: int = 120,
    ) -> Dict[str, Any]:
        """
        Lint Python code content directly

        Args:
            content: Python code to lint
            ignore_codes: Error codes to ignore
            max_line_length: Maximum line length

        Returns:
            Dictionary with lint results
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(content)
                temp_path = f.name

            # Build flake8 command
            ignore = ignore_codes or self.DEFAULT_IGNORE
            cmd = [
                "python", "-m", "flake8",
                temp_path,
                f"--max-line-length={max_line_length}",
                f"--ignore={','.join(ignore)}",
                "--format=%(row)d:%(col)d: %(code)s %(text)s",
            ]

            # Run flake8
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse output
            issues = []
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parsed = self._parse_content_lint_line(line)
                        if parsed:
                            issues.append(parsed)

            # Clean up
            os.unlink(temp_path)

            return {
                "success": True,
                "issues": issues,
                "issue_count": len(issues),
                "has_errors": len(issues) > 0,
            }

        except Exception as e:
            logger.error(f"Error linting content: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _parse_content_lint_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a flake8 output line for content linting"""
        import re
        
        # Pattern: line:col: code message
        pattern = r"(\d+):(\d+): ([A-Z]\d+) (.+)"
        match = re.match(pattern, line)
        
        if match:
            return {
                "line": int(match.group(1)),
                "column": int(match.group(2)),
                "code": match.group(3),
                "message": match.group(4),
                "severity": self._get_severity(match.group(3)),
            }
        return None

    def check_syntax(self, content: str) -> Dict[str, Any]:
        """
        Check Python syntax without full linting

        Args:
            content: Python code to check

        Returns:
            Dictionary with syntax check results
        """
        try:
            ast.parse(content)
            return {
                "success": True,
                "valid": True,
                "message": "Syntax is valid",
            }
        except SyntaxError as e:
            return {
                "success": True,
                "valid": False,
                "error": {
                    "message": str(e.msg),
                    "line": e.lineno,
                    "column": e.offset,
                    "text": e.text.strip() if e.text else None,
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def check_file_syntax(self, file_path: str) -> Dict[str, Any]:
        """
        Check syntax of a Python file

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with syntax check results
        """
        try:
            target_path = self._validate_path(file_path)

            if not target_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                }

            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read()

            result = self.check_syntax(content)
            result["file"] = str(target_path.relative_to(self.project_path))
            return result

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def lint_project(
        self,
        ignore_codes: Optional[List[str]] = None,
        max_line_length: int = 120,
        exclude_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Lint all Python files in the project

        Args:
            ignore_codes: Error codes to ignore
            max_line_length: Maximum line length
            exclude_dirs: Directories to exclude

        Returns:
            Dictionary with project-wide lint results
        """
        try:
            ignore = ignore_codes or self.DEFAULT_IGNORE
            exclude = exclude_dirs or [".git", ".venv", "venv", "__pycache__", "node_modules"]

            cmd = [
                "python", "-m", "flake8",
                str(self.project_path),
                f"--max-line-length={max_line_length}",
                f"--ignore={','.join(ignore)}",
                f"--exclude={','.join(exclude)}",
                "--format=%(path)s:%(row)d:%(col)d: %(code)s %(text)s",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.project_path),
            )

            # Parse output and group by file
            issues_by_file = {}
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parsed = self._parse_flake8_line(line)
                        if parsed:
                            file_path = parsed["file"]
                            if file_path not in issues_by_file:
                                issues_by_file[file_path] = []
                            issues_by_file[file_path].append(parsed)

            total_issues = sum(len(v) for v in issues_by_file.values())

            return {
                "success": True,
                "files_with_issues": len(issues_by_file),
                "total_issues": total_issues,
                "issues_by_file": issues_by_file,
                "has_errors": total_issues > 0,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Project linting timed out",
            }
        except Exception as e:
            logger.error(f"Error linting project: {e}")
            return {
                "success": False,
                "error": str(e),
            }
