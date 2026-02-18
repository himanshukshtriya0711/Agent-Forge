"""
Patch Applier Tool
Applies unified diff patches to files with validation
"""

import os
import re
import logging
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from django.conf import settings

logger = logging.getLogger("agentforge.tools")


class PatchApplier:
    """
    Applies unified diff patches to files
    Validates patches before applying and supports rollback
    """

    def __init__(self, project_path: Optional[Path] = None):
        """
        Initialize PatchApplier

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

    def parse_unified_diff(self, diff_content: str) -> Dict[str, Any]:
        """
        Parse a unified diff and extract information

        Args:
            diff_content: The unified diff string

        Returns:
            Dictionary with parsed diff information
        """
        result = {
            "source_file": None,
            "target_file": None,
            "hunks": [],
            "is_valid": False,
            "error": None,
        }

        lines = diff_content.strip().split("\n")
        if not lines:
            result["error"] = "Empty diff"
            return result

        # Parse header
        for i, line in enumerate(lines):
            if line.startswith("--- "):
                # Extract source file path
                match = re.match(r"^--- (?:a/)?(.+?)(?:\t|$)", line)
                if match:
                    result["source_file"] = match.group(1)
            elif line.startswith("+++ "):
                # Extract target file path
                match = re.match(r"^\+\+\+ (?:b/)?(.+?)(?:\t|$)", line)
                if match:
                    result["target_file"] = match.group(1)
            elif line.startswith("@@"):
                break

        # Parse hunks
        current_hunk = None
        hunk_pattern = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

        for line in lines:
            hunk_match = hunk_pattern.match(line)
            if hunk_match:
                if current_hunk:
                    result["hunks"].append(current_hunk)

                current_hunk = {
                    "source_start": int(hunk_match.group(1)),
                    "source_count": int(hunk_match.group(2) or 1),
                    "target_start": int(hunk_match.group(3)),
                    "target_count": int(hunk_match.group(4) or 1),
                    "lines": [],
                }
            elif current_hunk is not None:
                if line.startswith("+") or line.startswith("-") or line.startswith(" "):
                    current_hunk["lines"].append(line)
                elif line.startswith("\\"):
                    # No newline at end of file indicator
                    pass

        if current_hunk:
            result["hunks"].append(current_hunk)

        result["is_valid"] = bool(result["target_file"] and result["hunks"])
        return result

    def apply_patch(
        self,
        file_path: str,
        diff_content: str,
        create_backup: bool = True,
    ) -> Dict[str, Any]:
        """
        Apply a unified diff patch to a file

        Args:
            file_path: Path to the file to patch
            diff_content: The unified diff content
            create_backup: Whether to create a backup before patching

        Returns:
            Dictionary with operation result
        """
        try:
            target_path = self._validate_path(file_path)

            # Parse the diff
            parsed = self.parse_unified_diff(diff_content)
            if not parsed["is_valid"]:
                return {
                    "success": False,
                    "error": f"Invalid diff: {parsed.get('error', 'Could not parse')}",
                }

            # Read original file content
            if not target_path.exists():
                original_content = ""
                original_lines = []
            else:
                with open(target_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
                original_lines = original_content.split("\n")

            # Create backup if requested
            backup_path = None
            if create_backup and target_path.exists():
                from .file_writer import FileWriter
                writer = FileWriter(self.project_path)
                backup_path = writer._create_backup(target_path)

            # Apply hunks
            new_lines = original_lines.copy()
            offset = 0

            for hunk in parsed["hunks"]:
                new_lines, offset = self._apply_hunk(new_lines, hunk, offset)

            # Write patched content
            new_content = "\n".join(new_lines)
            
            # Ensure parent directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Applied patch to: {target_path}")

            return {
                "success": True,
                "file": str(target_path.relative_to(self.project_path)),
                "hunks_applied": len(parsed["hunks"]),
                "backup_path": str(backup_path) if backup_path else None,
                "lines_added": sum(
                    1 for h in parsed["hunks"] for l in h["lines"] if l.startswith("+")
                ),
                "lines_removed": sum(
                    1 for h in parsed["hunks"] for l in h["lines"] if l.startswith("-")
                ),
            }

        except Exception as e:
            logger.error(f"Error applying patch: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _apply_hunk(
        self, lines: List[str], hunk: Dict[str, Any], offset: int
    ) -> Tuple[List[str], int]:
        """
        Apply a single hunk to the file lines

        Args:
            lines: Current file lines
            hunk: Hunk information
            offset: Line offset from previous hunks

        Returns:
            Tuple of (new lines, new offset)
        """
        start_line = hunk["source_start"] - 1 + offset
        hunk_lines = hunk["lines"]

        new_lines = []
        removed_count = 0
        added_count = 0

        for line in hunk_lines:
            if line.startswith("-"):
                removed_count += 1
            elif line.startswith("+"):
                new_lines.append(line[1:])  # Remove the + prefix
                added_count += 1
            elif line.startswith(" "):
                new_lines.append(line[1:])  # Remove the space prefix
            else:
                new_lines.append(line)

        # Replace the affected lines
        end_line = start_line + hunk["source_count"]
        result = lines[:start_line] + new_lines + lines[end_line:]

        new_offset = offset + (added_count - removed_count)
        return result, new_offset

    def generate_diff(
        self, file_path: str, new_content: str
    ) -> Dict[str, Any]:
        """
        Generate a unified diff between current file content and new content

        Args:
            file_path: Path to the original file
            new_content: New content to compare against

        Returns:
            Dictionary with generated diff
        """
        import difflib

        try:
            target_path = self._validate_path(file_path)

            # Read original content
            if target_path.exists():
                with open(target_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
            else:
                original_content = ""

            # Generate unified diff
            original_lines = original_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)

            diff = difflib.unified_diff(
                original_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            )

            diff_content = "".join(diff)

            return {
                "success": True,
                "diff": diff_content,
                "has_changes": bool(diff_content.strip()),
                "file": file_path,
            }

        except Exception as e:
            logger.error(f"Error generating diff: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def preview_patch(self, file_path: str, diff_content: str) -> Dict[str, Any]:
        """
        Preview what a patch would do without applying it

        Args:
            file_path: Path to the file
            diff_content: The unified diff content

        Returns:
            Dictionary with preview information
        """
        try:
            target_path = self._validate_path(file_path)
            parsed = self.parse_unified_diff(diff_content)

            if not parsed["is_valid"]:
                return {
                    "success": False,
                    "error": f"Invalid diff: {parsed.get('error', 'Could not parse')}",
                }

            # Read original content
            if target_path.exists():
                with open(target_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
            else:
                original_content = ""

            # Apply hunks to get preview
            original_lines = original_content.split("\n")
            new_lines = original_lines.copy()
            offset = 0

            for hunk in parsed["hunks"]:
                new_lines, offset = self._apply_hunk(new_lines, hunk, offset)

            return {
                "success": True,
                "file": file_path,
                "original_content": original_content,
                "patched_content": "\n".join(new_lines),
                "hunks": len(parsed["hunks"]),
                "lines_added": sum(
                    1 for h in parsed["hunks"] for l in h["lines"] if l.startswith("+")
                ),
                "lines_removed": sum(
                    1 for h in parsed["hunks"] for l in h["lines"] if l.startswith("-")
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
