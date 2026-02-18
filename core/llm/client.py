"""
Groq LLM Client
Wrapper for Groq API with Llama models
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List

from groq import Groq
from django.conf import settings

logger = logging.getLogger("agentforge.llm")


class GroqClient:
    """
    Client for interacting with Groq API (Llama models)
    Provides methods for chat completion and JSON output
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
    ):
        """
        Initialize Groq client

        Args:
            api_key: Groq API key (defaults to settings)
            model: Model name (defaults to settings)
            temperature: Generation temperature
            max_tokens: Maximum tokens in response
        """
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model_name = model or settings.GROQ_MODEL
        self.temperature = temperature
        self.max_tokens = max_tokens

        if not self.api_key:
            raise ValueError("GROQ_API_KEY not configured. Set it in .env file.")

        self.client = Groq(api_key=self.api_key)

        logger.info(f"Initialized GroqClient with model: {self.model_name}")

    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Send a chat message and get a response

        Args:
            user_message: The user's message
            system_prompt: Optional system prompt
            chat_history: Optional list of previous messages

        Returns:
            The assistant's response as a string
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        if chat_history:
            for msg in chat_history:
                messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", "")
                })

        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            result = response.choices[0].message.content
            logger.debug(f"Chat response length: {len(result)} chars")
            return result

        except Exception as e:
            logger.error(f"Error calling Groq API: {e}")
            raise

    def chat_json(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat message and parse response as JSON

        Args:
            user_message: The user's message
            system_prompt: Optional system prompt
            chat_history: Optional list of previous messages

        Returns:
            Parsed JSON response as dictionary
        """
        json_instruction = """
IMPORTANT: Your response must be valid JSON only.
Do not include any text before or after the JSON.
Do not use markdown code blocks.
"""
        enhanced_system = (
            f"{system_prompt}\n\n{json_instruction}" if system_prompt else json_instruction
        )

        response = self.chat(
            user_message=user_message,
            system_prompt=enhanced_system,
            chat_history=chat_history,
        )

        # Clean response and parse JSON
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response}")
            return self._extract_json(response)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """
        Attempt to extract JSON from text that may contain extra content
        """
        import re

        # Try to find JSON object
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Return error indicator
        return {"error": "Failed to parse response", "raw_response": text[:500]}


# Alias for backward compatibility
GeminiClient = GroqClient

