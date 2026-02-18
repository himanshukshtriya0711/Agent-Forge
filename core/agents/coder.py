"""
Coder Agent
Writes and modifies code with diff-based patches
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

from .base import BaseAgent
from ..llm import PromptTemplates

logger = logging.getLogger("agentforge.agents")


class CoderAgent(BaseAgent):
    """
    Coder agent that writes and modifies code
    Uses diff-based patches for modifications
    """

    # Maximum lint retry attempts
    MAX_LINT_RETRIES = 3

    @property
    def system_prompt(self) -> str:
        return PromptTemplates.CODER

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a coding task

        Args:
            task: Task with 'action', 'file_path', 'description'

        Returns:
            Result with generated code or patch
        """
        action = task.get("action", "CREATE").upper()
        file_path = task.get("file_path", "")
        description = task.get("description", "")
        context = task.get("context", "")
        validate_lint = task.get("validate_lint", True)

        logger.info(f"CoderAgent: {action} - {file_path or 'new file'}")

        # Get relevant code context
        code_context = ""
        if self.rag:
            code_context = self.get_code_context(description)

        # Read existing file if modifying
        existing_content = ""
        if action == "MODIFY" and file_path:
            file_result = self.read_file(file_path)
            if file_result["success"]:
                existing_content = file_result["content"]
            else:
                logger.warning(f"Could not read file {file_path}: {file_result.get('error')}")

        # Build context for LLM
        full_context = f"""
## Task Description
{description}

## Additional Context
{context}

## Relevant Code from Project
{code_context}

## Target File: {file_path if file_path else 'New file to be created'}

## Existing File Content
```python
{existing_content if existing_content else "# New file - no existing content"}
```
"""

        # Generate code
        result = self.think(
            user_message=f"Please {action.lower()} the code as described.",
            context=full_context,
            return_json=True,
        )

        if "error" in result:
            return {
                "success": False,
                "error": result["error"],
            }

        # Validate and process result
        return self._process_result(result, action, file_path, validate_lint)

    def _process_result(
        self,
        result: Dict[str, Any],
        action: str,
        file_path: str,
        validate_lint: bool,
    ) -> Dict[str, Any]:
        """
        Process the LLM result and optionally validate/apply

        Args:
            result: LLM response
            action: CREATE or MODIFY
            file_path: Target file path
            validate_lint: Whether to lint validate

        Returns:
            Processed result
        """
        content = result.get("content", "")
        explanation = result.get("explanation", "")

        if not content:
            return {
                "success": False,
                "error": "No code generated",
            }

        # For CREATE action, validate the full content
        if action == "CREATE":
            if validate_lint and file_path and file_path.endswith(".py"):
                lint_result = self._validate_and_fix(content, action)
                if lint_result["fixed"]:
                    content = lint_result["content"]

            return {
                "success": True,
                "action": action,
                "file_path": result.get("file_path", file_path),
                "content": content,
                "explanation": explanation,
                "imports_needed": result.get("imports_needed", []),
                "dependencies": result.get("dependencies", []),
            }

        # For MODIFY action, we have a diff
        elif action == "MODIFY":
            diff_content = content

            # Validate diff format
            if not diff_content.startswith("---") and not diff_content.startswith("@@"):
                # LLM might have returned full content instead of diff
                logger.warning("LLM returned full content instead of diff, generating diff")
                
                if file_path:
                    diff_result = self.patch_applier.generate_diff(file_path, content)
                    if diff_result["success"]:
                        diff_content = diff_result["diff"]
                    else:
                        # Fall back to treating as full content replacement
                        return {
                            "success": True,
                            "action": "REPLACE",
                            "file_path": file_path,
                            "content": content,
                            "explanation": explanation,
                        }

            # Preview the patch
            preview = None
            if file_path and self.patch_applier:
                preview = self.patch_applier.preview_patch(file_path, diff_content)

            return {
                "success": True,
                "action": action,
                "file_path": file_path,
                "diff": diff_content,
                "explanation": explanation,
                "preview": preview,
            }

        return {
            "success": False,
            "error": f"Unknown action: {action}",
        }

    def _validate_and_fix(
        self,
        content: str,
        action: str,
        retries: int = 0,
    ) -> Dict[str, Any]:
        """
        Validate code with linter and attempt to fix issues

        Args:
            content: Code content
            action: The action type
            retries: Current retry count

        Returns:
            Dict with 'content' and 'fixed' flag
        """
        if retries >= self.MAX_LINT_RETRIES:
            logger.warning("Max lint retries reached, returning as-is")
            return {"content": content, "fixed": False}

        # Check syntax first
        syntax_result = self.check_syntax(content)
        if not syntax_result.get("valid", False):
            error = syntax_result.get("error", {})
            logger.info(f"Syntax error found, attempting fix (retry {retries + 1})")

            # Ask LLM to fix
            fix_prompt = f"""
The following code has a syntax error:

```python
{content}
```

Error: {error.get('message', 'Unknown')} at line {error.get('line', '?')}

Please fix the syntax error and return the corrected code.
Return ONLY the corrected code, no explanations.
"""
            fixed_result = self.llm.chat(
                user_message=fix_prompt,
                system_prompt="You are a code fixer. Return only valid Python code.",
            )

            # Clean response
            fixed_content = self._clean_code_response(fixed_result)
            return self._validate_and_fix(fixed_content, action, retries + 1)

        # Run linter
        lint_result = self.lint_content(content)
        if lint_result.get("has_errors", False) and lint_result.get("issue_count", 0) > 0:
            # Filter for actual errors (not warnings)
            errors = [
                issue for issue in lint_result.get("issues", [])
                if issue.get("severity") == "error"
            ]

            if errors:
                logger.info(f"Lint errors found: {len(errors)}, attempting fix")

                fix_prompt = f"""
The following code has lint errors:

```python
{content}
```

Errors:
{chr(10).join(f"- Line {e['line']}: {e['code']} - {e['message']}" for e in errors[:5])}

Please fix these errors and return the corrected code.
Return ONLY the corrected code, no explanations.
"""
                fixed_result = self.llm.chat(
                    user_message=fix_prompt,
                    system_prompt="You are a code fixer. Return only valid Python code.",
                )

                fixed_content = self._clean_code_response(fixed_result)
                return self._validate_and_fix(fixed_content, action, retries + 1)

        return {"content": content, "fixed": retries > 0}

    def _clean_code_response(self, response: str) -> str:
        """Clean code from LLM response"""
        response = response.strip()
        
        # Remove markdown code blocks
        if response.startswith("```python"):
            response = response[9:]
        elif response.startswith("```"):
            response = response[3:]
        
        if response.endswith("```"):
            response = response[:-3]
        
        return response.strip()

    def create_file(
        self,
        file_path: str,
        description: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Create a new file

        Args:
            file_path: Path for the new file
            description: What the file should contain
            context: Additional context

        Returns:
            Result with file content
        """
        return self.execute({
            "action": "CREATE",
            "file_path": file_path,
            "description": description,
            "context": context,
        })

    def modify_file(
        self,
        file_path: str,
        description: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Modify an existing file

        Args:
            file_path: Path to the file
            description: What modifications to make
            context: Additional context

        Returns:
            Result with diff patch
        """
        return self.execute({
            "action": "MODIFY",
            "file_path": file_path,
            "description": description,
            "context": context,
        })
