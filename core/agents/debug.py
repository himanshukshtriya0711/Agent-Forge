"""
Debug Agent
Analyzes errors and proposes fixes
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .base import BaseAgent
from ..llm import PromptTemplates

logger = logging.getLogger("agentforge.agents")


class DebugAgent(BaseAgent):
    """
    Debug agent that analyzes errors and proposes fixes
    """

    @property
    def system_prompt(self) -> str:
        return PromptTemplates.DEBUG

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze an error and propose a fix

        Args:
            task: Task with 'error', 'file_path', 'context'

        Returns:
            Diagnosis and fix proposal
        """
        error_message = task.get("error", "")
        file_path = task.get("file_path", "")
        context = task.get("context", "")
        stack_trace = task.get("stack_trace", "")

        logger.info(f"DebugAgent: Analyzing error in {file_path or 'unknown file'}")

        # Read the problematic file
        file_content = ""
        if file_path:
            file_result = self.read_file(file_path)
            if file_result["success"]:
                file_content = file_result["content"]

        # Get relevant code context from RAG
        code_context = ""
        if self.rag:
            search_query = f"{error_message} {file_path}"
            code_context = self.get_code_context(search_query)

        # Build full context
        full_context = f"""
## Error Message
```
{error_message}
```

## Stack Trace
```
{stack_trace if stack_trace else "Not provided"}
```

## File: {file_path}
```python
{file_content if file_content else "Could not read file"}
```

## Additional Context
{context}

## Related Code from Project
{code_context}

## Project Structure
```
{self.get_project_structure() if self.file_reader else "Unknown"}
```
"""

        # Analyze and diagnose
        result = self.think(
            user_message="Analyze this error and propose a fix.",
            context=full_context,
            return_json=True,
        )

        if "error" in result and "error_type" not in result:
            return {
                "success": False,
                "error": result["error"],
            }

        # Validate fix if provided
        fix_proposal = result.get("fix_proposal", {})
        if fix_proposal and fix_proposal.get("diff"):
            # Preview the fix
            if file_path and self.patch_applier:
                preview = self.patch_applier.preview_patch(
                    file_path,
                    fix_proposal["diff"],
                )
                fix_proposal["preview"] = preview

        return {
            "success": True,
            "error_type": result.get("error_type", "UNKNOWN"),
            "root_cause": result.get("root_cause", "Unknown"),
            "affected_files": result.get("affected_files", [file_path] if file_path else []),
            "fix_proposal": fix_proposal,
            "prevention_tips": result.get("prevention_tips", []),
            "confidence": result.get("confidence", 0.5),
        }

    def analyze_lint_errors(
        self,
        file_path: str,
    ) -> Dict[str, Any]:
        """
        Analyze lint errors in a file and suggest fixes

        Args:
            file_path: Path to the file

        Returns:
            Analysis and fixes
        """
        # Run linter
        lint_result = self.lint_file(file_path)
        
        if not lint_result.get("success"):
            return lint_result

        if not lint_result.get("has_errors"):
            return {
                "success": True,
                "message": "No lint errors found",
                "issues": [],
            }

        issues = lint_result.get("issues", [])

        # Read file content
        file_result = self.read_file(file_path)
        file_content = file_result.get("content", "") if file_result["success"] else ""

        # Ask for fixes
        fix_prompt = f"""
The following file has lint issues:

File: {file_path}
```python
{file_content}
```

Lint Issues:
{chr(10).join(f"- Line {i['line']}: [{i['code']}] {i['message']}" for i in issues[:10])}

For each issue, explain the problem and provide a fix.
"""

        result = self.think(
            user_message=fix_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "file": file_path,
            "issue_count": len(issues),
            "issues": issues,
            "analysis": result,
        }

    def analyze_test_failure(
        self,
        test_output: str,
        test_file: str = "",
    ) -> Dict[str, Any]:
        """
        Analyze a test failure

        Args:
            test_output: Test output/error
            test_file: Test file path

        Returns:
            Analysis and fix suggestions
        """
        context = f"""
## Test Output
```
{test_output}
```

## Test File
{test_file if test_file else "Not specified"}
"""

        # Get test file content
        if test_file:
            test_content = self.read_file(test_file)
            if test_content["success"]:
                context += f"""

## Test File Content
```python
{test_content['content']}
```
"""

        result = self.think(
            user_message="Analyze this test failure and suggest fixes.",
            context=context,
            return_json=True,
        )

        return {
            "success": True,
            "analysis": result,
            "test_file": test_file,
        }

    def suggest_debugging_steps(
        self,
        description: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Suggest debugging steps for an issue

        Args:
            description: Description of the issue
            context: Additional context

        Returns:
            List of debugging steps
        """
        debug_prompt = f"""
A developer is experiencing this issue:

{description}

Context: {context}

Suggest step-by-step debugging approaches to identify and fix the issue.
Include:
1. What to check first
2. How to isolate the problem
3. What logs/output to examine
4. Potential root causes
"""

        result = self.think(
            user_message=debug_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "debugging_steps": result,
        }

    def trace_error(
        self,
        error: str,
        entry_file: str,
    ) -> Dict[str, Any]:
        """
        Trace an error through the codebase

        Args:
            error: Error message
            entry_file: File where error was raised

        Returns:
            Trace analysis
        """
        # Read entry file
        entry_content = self.read_file(entry_file)

        # Get related files from RAG
        code_context = ""
        if self.rag:
            code_context = self.get_code_context(error, top_k=10)

        trace_prompt = f"""
Trace this error through the codebase:

Error: {error}
Entry file: {entry_file}

Entry file content:
```python
{entry_content.get('content', 'Could not read') if entry_content['success'] else 'Could not read'}
```

Related code:
{code_context}

Identify:
1. The exact line causing the error
2. The call chain leading to the error
3. All files involved
4. The root cause
"""

        result = self.think(
            user_message=trace_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "trace": result,
        }
