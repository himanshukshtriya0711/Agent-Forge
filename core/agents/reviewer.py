"""
Reviewer Agent
Reviews code for quality, security, and best practices
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .base import BaseAgent
from ..llm import PromptTemplates

logger = logging.getLogger("agentforge.agents")


class ReviewerAgent(BaseAgent):
    """
    Reviewer agent that reviews code for quality and best practices
    """

    @property
    def system_prompt(self) -> str:
        return PromptTemplates.REVIEWER

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Review code

        Args:
            task: Task with 'code' or 'file_path', 'focus_areas'

        Returns:
            Review results with issues and suggestions
        """
        code = task.get("code", "")
        file_path = task.get("file_path", "")
        focus_areas = task.get("focus_areas", [])
        include_suggestions = task.get("include_suggestions", True)

        logger.info(f"ReviewerAgent: Reviewing {file_path or 'provided code'}")

        # Get code content
        if not code and file_path:
            file_result = self.read_file(file_path)
            if file_result["success"]:
                code = file_result["content"]
            else:
                return {
                    "success": False,
                    "error": f"Could not read file: {file_result.get('error')}",
                }

        if not code:
            return {
                "success": False,
                "error": "No code provided for review",
            }

        # Get project context for comparison
        code_context = ""
        if self.rag:
            code_context = self.get_code_context(
                f"similar code to {file_path}" if file_path else "code patterns",
                top_k=3,
            )

        # Build review context
        full_context = f"""
## Code to Review
**File:** {file_path if file_path else "Provided snippet"}

```python
{code}
```

## Focus Areas
{', '.join(focus_areas) if focus_areas else 'General review - check everything'}

## Similar Code in Project (for style consistency)
{code_context}

## Project Structure
```
{self.get_project_structure() if self.file_reader else "Unknown"}
```
"""

        # Perform review
        review_prompt = """
Review the provided code thoroughly. Check for:
1. Security vulnerabilities
2. Performance issues
3. Code style and readability
4. Error handling
5. Logic errors
6. Best practices violations

Provide constructive feedback with specific line numbers and suggestions.
"""

        result = self.think(
            user_message=review_prompt,
            context=full_context,
            return_json=True,
        )

        if "error" in result and "overall_rating" not in result:
            return {
                "success": False,
                "error": result["error"],
            }

        # Enrich with lint results
        lint_issues = []
        if file_path and file_path.endswith(".py"):
            lint_result = self.lint_content(code)
            if lint_result.get("success") and lint_result.get("issues"):
                lint_issues = lint_result["issues"]

        return {
            "success": True,
            "file_path": file_path,
            "overall_rating": result.get("overall_rating", "GOOD"),
            "summary": result.get("summary", ""),
            "issues": result.get("issues", []),
            "lint_issues": lint_issues,
            "positive_aspects": result.get("positive_aspects", []),
            "suggested_improvements": result.get("suggested_improvements", []) if include_suggestions else [],
        }

    def review_diff(
        self,
        diff: str,
        file_path: str = "",
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Review a diff/patch before applying

        Args:
            diff: The unified diff
            file_path: Target file path
            context: Additional context

        Returns:
            Review results
        """
        review_prompt = f"""
## Diff to Review
**Target File:** {file_path if file_path else "Unknown"}

```diff
{diff}
```

## Context
{context}

Review this diff for:
1. Correctness - does it do what's intended?
2. Completeness - are all necessary changes included?
3. Side effects - could this break anything?
4. Style - does it follow project conventions?

Approve or reject with detailed reasoning.
"""

        result = self.think(
            user_message=review_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "file_path": file_path,
            "approved": result.get("approved", False),
            "review": result,
        }

    def review_plan(
        self,
        plan: Dict[str, Any],
        original_request: str = "",
    ) -> Dict[str, Any]:
        """
        Review a plan before execution

        Args:
            plan: The plan to review
            original_request: Original user request

        Returns:
            Plan review results
        """
        review_prompt = f"""
## Original Request
{original_request}

## Proposed Plan
{plan}

Review this plan for:
1. Completeness - does it address the full request?
2. Correctness - are the steps logical and accurate?
3. Safety - are there any risky operations?
4. Efficiency - could it be done better?

Approve the plan or suggest modifications.
"""

        result = self.think(
            user_message=review_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "plan_approved": result.get("approved", False),
            "review": result,
        }

    def compare_implementations(
        self,
        impl1: str,
        impl2: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """
        Compare two implementations and recommend the better one

        Args:
            impl1: First implementation
            impl2: Second implementation
            description: What the code should do

        Returns:
            Comparison results and recommendation
        """
        compare_prompt = f"""
## Task Description
{description}

## Implementation 1
```python
{impl1}
```

## Implementation 2
```python
{impl2}
```

Compare these implementations on:
1. Correctness
2. Performance
3. Readability
4. Maintainability
5. Error handling

Recommend the better implementation with detailed reasoning.
"""

        result = self.think(
            user_message=compare_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "comparison": result,
        }

    def security_audit(
        self,
        code: str,
        file_path: str = "",
    ) -> Dict[str, Any]:
        """
        Perform a security-focused audit

        Args:
            code: Code to audit
            file_path: File path

        Returns:
            Security audit results
        """
        audit_prompt = f"""
## Security Audit Request

**File:** {file_path}

```python
{code}
```

Perform a security audit. Check for:
1. SQL injection vulnerabilities
2. XSS vulnerabilities
3. Authentication/authorization issues
4. Sensitive data exposure
5. Input validation issues
6. Insecure dependencies
7. Hardcoded secrets
8. Path traversal vulnerabilities

Rate severity as CRITICAL, HIGH, MEDIUM, LOW, or INFO.
"""

        result = self.think(
            user_message=audit_prompt,
            return_json=True,
        )

        return {
            "success": True,
            "file_path": file_path,
            "audit_results": result,
        }
