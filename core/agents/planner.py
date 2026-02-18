"""
Planner Agent
Creates detailed plans for complex coding tasks
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .base import BaseAgent
from ..llm import PromptTemplates

logger = logging.getLogger("agentforge.agents")


class PlannerAgent(BaseAgent):
    """
    Planner agent that breaks down complex tasks into actionable steps
    """

    @property
    def system_prompt(self) -> str:
        return PromptTemplates.PLANNER

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a plan for the given task

        Args:
            task: Task specification with 'description' and optional 'context'

        Returns:
            Plan with steps and metadata
        """
        description = task.get("description", "")
        context = task.get("context", "")
        use_rag = task.get("use_rag", True)

        logger.info(f"PlannerAgent: Creating plan for: {description[:100]}...")

        # Get code context if RAG is available
        code_context = ""
        if use_rag and self.rag:
            code_context = self.get_code_context(description)

        # Get project structure
        project_structure = ""
        if self.file_reader:
            project_structure = self.get_project_structure()

        # Build full context
        full_context = f"""
## User Request
{description}

## Additional Context
{context if context else "None provided"}

## Relevant Code from Project
{code_context if code_context else "No code context available"}

## Project Structure
```
{project_structure if project_structure else "Unknown"}
```
"""

        # Generate plan
        plan_prompt = """
Based on the above context, create a detailed plan to accomplish the user's request.
Break down the task into specific, actionable steps that can be executed by specialized agents.

Consider:
1. What files need to be read/analyzed
2. What code needs to be written or modified
3. What tests should be run
4. What order the steps should be executed
"""

        result = self.think(
            user_message=plan_prompt,
            context=full_context,
            return_json=True,
        )

        if "error" in result:
            logger.error(f"PlannerAgent error: {result['error']}")
            return {
                "success": False,
                "error": result["error"],
            }

        # Validate and enhance plan
        plan = self._validate_plan(result)

        return {
            "success": True,
            "plan": plan,
            "step_count": len(plan.get("steps", [])),
        }

    def _validate_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and enhance the generated plan

        Args:
            plan: Raw plan from LLM

        Returns:
            Validated and enhanced plan
        """
        # Ensure required fields exist
        if "steps" not in plan:
            plan["steps"] = []

        if "plan_summary" not in plan:
            plan["plan_summary"] = "Plan generated"

        if "estimated_complexity" not in plan:
            plan["estimated_complexity"] = "MEDIUM"

        if "potential_risks" not in plan:
            plan["potential_risks"] = []

        # Validate each step
        valid_actions = {"ANALYZE", "CREATE", "MODIFY", "DELETE", "TEST", "REVIEW"}
        valid_agents = {"CODER", "DEBUG", "REVIEWER", "EXECUTOR", "PLANNER"}

        for i, step in enumerate(plan["steps"]):
            # Ensure step number
            if "step_number" not in step:
                step["step_number"] = i + 1

            # Validate action
            if step.get("action", "").upper() not in valid_actions:
                step["action"] = "ANALYZE"

            # Validate agent assignment
            if step.get("agent", "").upper() not in valid_agents:
                # Auto-assign based on action
                action = step.get("action", "").upper()
                if action in ("CREATE", "MODIFY"):
                    step["agent"] = "CODER"
                elif action == "DELETE":
                    step["agent"] = "EXECUTOR"
                elif action == "TEST":
                    step["agent"] = "EXECUTOR"
                elif action == "REVIEW":
                    step["agent"] = "REVIEWER"
                else:
                    step["agent"] = "CODER"

        return plan

    def refine_plan(
        self,
        original_plan: Dict[str, Any],
        feedback: str,
    ) -> Dict[str, Any]:
        """
        Refine an existing plan based on feedback

        Args:
            original_plan: The original plan
            feedback: Feedback for refinement

        Returns:
            Refined plan
        """
        refine_prompt = f"""
## Original Plan
{original_plan}

## Feedback
{feedback}

Please refine the plan based on the feedback. Keep what works and improve what doesn't.
"""

        result = self.think(
            user_message=refine_prompt,
            return_json=True,
        )

        if "error" in result:
            return {
                "success": False,
                "error": result["error"],
            }

        return {
            "success": True,
            "plan": self._validate_plan(result),
            "refined": True,
        }

    def estimate_effort(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Estimate the effort required for a task

        Args:
            task: Task specification

        Returns:
            Effort estimate
        """
        estimate_prompt = f"""
Estimate the effort required for this task:

{task.get('description', '')}

Provide your estimate as:
1. Complexity: LOW, MEDIUM, HIGH
2. Estimated steps: number
3. Risk level: LOW, MEDIUM, HIGH
4. Recommended approach: brief description
"""

        return self.think(
            user_message=estimate_prompt,
            return_json=True,
        )
