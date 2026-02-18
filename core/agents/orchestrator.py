"""
Orchestrator
Coordinates multi-agent workflow for complex tasks
Uses AutoGen-style coordination with Groq LLM
"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from enum import Enum

from .base import BaseAgent
from .planner import PlannerAgent
from .coder import CoderAgent
from .debug import DebugAgent
from .reviewer import ReviewerAgent
from .executor import ExecutorAgent
from ..llm import GroqClient, PromptTemplates

logger = logging.getLogger("agentforge.agents")


class AgentType(Enum):
    """Available agent types"""
    PLANNER = "PLANNER"
    CODER = "CODER"
    DEBUG = "DEBUG"
    REVIEWER = "REVIEWER"
    EXECUTOR = "EXECUTOR"


class Orchestrator:
    """
    Orchestrator that coordinates the multi-agent system
    
    Flow: User → Orchestrator → Planner → [Coder/Debug] → Reviewer → Executor
    """

    def __init__(
        self,
        project_path: Optional[Path] = None,
        auto_apply: bool = False,
        max_iterations: int = 10,
    ):
        """
        Initialize Orchestrator

        Args:
            project_path: Path to the project
            auto_apply: Automatically apply changes
            max_iterations: Maximum planning iterations
        """
        self.project_path = Path(project_path) if project_path else None
        self.auto_apply = auto_apply
        self.max_iterations = max_iterations

        # Initialize LLM (Groq)
        self.llm = GroqClient()
        
        # RAG is optional (disabled for now)
        self.rag = None

        # Initialize agents
        self._init_agents()

        # Execution state
        self.current_plan = None
        self.execution_history: List[Dict[str, Any]] = []

        logger.info(f"Orchestrator initialized for project: {self.project_path}")

    def _init_agents(self):
        """Initialize all agent instances"""
        common_kwargs = {
            "project_path": self.project_path,
            "llm_client": self.llm,
        }

        self.agents = {
            AgentType.PLANNER: PlannerAgent(**common_kwargs),
            AgentType.CODER: CoderAgent(**common_kwargs),
            AgentType.DEBUG: DebugAgent(**common_kwargs),
            AgentType.REVIEWER: ReviewerAgent(**common_kwargs),
            AgentType.EXECUTOR: ExecutorAgent(**common_kwargs),
        }

    def process_request(
        self,
        user_request: str,
        context: str = "",
    ) -> Dict[str, Any]:
        """
        Process a user request through the multi-agent system

        Args:
            user_request: The user's request
            context: Additional context

        Returns:
            Processing results with plan and execution details
        """
        logger.info(f"Processing request: {user_request[:100]}...")

        # Reset state
        self.execution_history = []
        results = {
            "request": user_request,
            "steps": [],
            "final_result": None,
            "success": False,
        }

        try:
            # Step 1: Analyze and route the request
            routing = self._route_request(user_request, context)
            results["routing"] = routing

            # Step 2: Get or create plan
            if routing["requires_planning"]:
                plan_result = self._create_plan(user_request, context)
                if not plan_result["success"]:
                    results["error"] = plan_result.get("error", "Planning failed")
                    return results
                self.current_plan = plan_result["plan"]
                results["plan"] = self.current_plan
            else:
                # Direct execution for simple tasks
                self.current_plan = {
                    "steps": [{
                        "step_number": 1,
                        "action": "EXECUTE",
                        "agent": routing["primary_agent"],
                        "description": user_request,
                    }]
                }

            # Step 3: Execute plan steps
            for step in self.current_plan.get("steps", []):
                step_result = self._execute_step(step, context)
                results["steps"].append(step_result)

                # Check if step failed and should stop
                if not step_result.get("success", False):
                    if step_result.get("fatal", False):
                        results["error"] = f"Step {step['step_number']} failed: {step_result.get('error')}"
                        return results

            # Step 4: Compile final result
            results["success"] = True
            results["final_result"] = self._compile_results(results["steps"])

        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            results["error"] = str(e)

        return results

    def _route_request(
        self,
        request: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Analyze request and determine routing

        Args:
            request: User request
            context: Additional context

        Returns:
            Routing decision
        """
        routing_prompt = f"""
Analyze this request and determine how to handle it:

Request: {request}
Context: {context}

Determine:
1. Primary agent to use (PLANNER, CODER, DEBUG, REVIEWER, EXECUTOR)
2. Whether this requires a multi-step plan
3. Whether RAG context is needed
4. Confidence level (0-1)
"""

        response = self.llm.chat_json(
            user_message=routing_prompt,
            system_prompt=PromptTemplates.ORCHESTRATOR,
        )

        # Parse and validate response
        primary_agent = response.get("primary_agent", "PLANNER").upper()
        if primary_agent not in [a.value for a in AgentType]:
            primary_agent = "PLANNER"

        requires_planning = response.get("requires_planning", True)
        if primary_agent == "PLANNER":
            requires_planning = True

        return {
            "primary_agent": primary_agent,
            "requires_planning": requires_planning,
            "requires_rag": response.get("requires_rag", True),
            "confidence": response.get("confidence", 0.5),
            "analysis": response.get("analysis", ""),
        }

    def _create_plan(
        self,
        request: str,
        context: str,
    ) -> Dict[str, Any]:
        """
        Create an execution plan

        Args:
            request: User request
            context: Additional context

        Returns:
            Plan result
        """
        planner = self.agents[AgentType.PLANNER]

        # Index project if not done
        if self.rag:
            index_result = self.rag.index_project()
            logger.info(f"RAG index: {index_result.get('document_count', 0)} documents")

        return planner.execute({
            "description": request,
            "context": context,
            "use_rag": True,
        })

    def _execute_step(
        self,
        step: Dict[str, Any],
        context: str,
    ) -> Dict[str, Any]:
        """
        Execute a single plan step

        Args:
            step: Step specification
            context: Additional context

        Returns:
            Step execution result
        """
        step_number = step.get("step_number", 0)
        agent_type = step.get("agent", "CODER").upper()
        action = step.get("action", "").upper()
        description = step.get("description", "")
        target_file = step.get("target_file")

        logger.info(f"Executing step {step_number}: {agent_type} - {action}")

        try:
            agent_enum = AgentType[agent_type]
        except KeyError:
            agent_enum = AgentType.CODER

        agent = self.agents[agent_enum]

        # Build task for agent
        task = {
            "action": action,
            "description": description,
            "context": context,
            "file_path": target_file,
        }

        # Execute agent
        result = agent.execute(task)

        # Record in history
        execution_record = {
            "step": step_number,
            "agent": agent_type,
            "action": action,
            "result": result,
        }
        self.execution_history.append(execution_record)

        # Handle special cases
        if agent_type == "CODER" and result.get("success"):
            # Review if we got code
            if result.get("diff") or result.get("content"):
                review_result = self._review_code_change(result, step)
                result["review"] = review_result

                # Apply if auto-apply and approved
                if self.auto_apply and review_result.get("approved", False):
                    apply_result = self._apply_change(result)
                    result["applied"] = apply_result

        return {
            "success": result.get("success", False),
            "step_number": step_number,
            "agent": agent_type,
            "result": result,
        }

    def _review_code_change(
        self,
        coder_result: Dict[str, Any],
        step: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Review a code change before applying

        Args:
            coder_result: Result from coder agent
            step: The step that produced this code

        Returns:
            Review result
        """
        reviewer = self.agents[AgentType.REVIEWER]

        if coder_result.get("diff"):
            return reviewer.review_diff(
                diff=coder_result["diff"],
                file_path=coder_result.get("file_path", ""),
                context=step.get("description", ""),
            )
        elif coder_result.get("content"):
            return reviewer.execute({
                "code": coder_result["content"],
                "file_path": coder_result.get("file_path", ""),
            })

        return {"approved": False, "reason": "No code to review"}

    def _apply_change(
        self,
        coder_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Apply a code change

        Args:
            coder_result: Result from coder agent

        Returns:
            Application result
        """
        executor = self.agents[AgentType.EXECUTOR]
        file_path = coder_result.get("file_path", "")

        if coder_result.get("action") == "CREATE" or coder_result.get("action") == "REPLACE":
            return executor.execute({
                "action": "CREATE_FILE",
                "file_path": file_path,
                "content": coder_result.get("content", ""),
            })
        elif coder_result.get("diff"):
            return executor.execute({
                "action": "APPLY_PATCH",
                "file_path": file_path,
                "diff": coder_result["diff"],
            })

        return {"success": False, "error": "No applicable change"}

    def _compile_results(
        self,
        steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Compile step results into a final result

        Args:
            steps: List of step results

        Returns:
            Compiled final result
        """
        changes = []
        errors = []
        suggestions = []

        for step in steps:
            result = step.get("result", {})

            # Collect changes
            if result.get("diff"):
                changes.append({
                    "type": "diff",
                    "file": result.get("file_path"),
                    "diff": result["diff"],
                    "review": result.get("review"),
                    "applied": result.get("applied"),
                })
            elif result.get("content") and step.get("agent") == "CODER":
                changes.append({
                    "type": "create",
                    "file": result.get("file_path"),
                    "content": result["content"],
                    "applied": result.get("applied"),
                })

            # Collect errors
            if result.get("error"):
                errors.append({
                    "step": step.get("step_number"),
                    "error": result["error"],
                })

            # Collect suggestions from reviewer
            if result.get("suggested_improvements"):
                suggestions.extend(result["suggested_improvements"])

        return {
            "changes": changes,
            "errors": errors,
            "suggestions": suggestions,
            "total_steps": len(steps),
            "successful_steps": sum(1 for s in steps if s.get("success")),
        }

    def chat(
        self,
        message: str,
        session_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Simple chat interface for quick interactions

        Args:
            message: User message
            session_history: Optional conversation history

        Returns:
            Response with potential actions
        """
        # Determine if this is a simple question or an action request
        is_action = any(
            keyword in message.lower()
            for keyword in ["create", "modify", "fix", "debug", "write", "add", "update", "delete", "implement"]
        )

        if is_action:
            return self.process_request(message)

        # Simple question - use RAG to provide context
        context = ""
        if self.rag:
            context = self.rag.get_context(message, top_k=3)

        response = self.llm.chat(
            user_message=message,
            system_prompt="""You are AgentForge, an AI coding assistant. 
Answer questions about the codebase and help with coding tasks.
Be concise and helpful.""",
            chat_history=session_history,
        )

        return {
            "success": True,
            "response": response,
            "is_action": False,
            "context_used": bool(context),
        }

    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status"""
        return {
            "project_path": str(self.project_path) if self.project_path else None,
            "auto_apply": self.auto_apply,
            "agents": list(self.agents.keys()),
            "rag_indexed": self.rag.get_stats() if self.rag else None,
            "history_length": len(self.execution_history),
        }
