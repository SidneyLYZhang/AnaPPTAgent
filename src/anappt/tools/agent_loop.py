"""Agent loop with tool-calling support for AnaPPTAgent.

Implements a ReAct-style loop where the LLM can call tools iteratively
until it produces a final text answer. All calls are synchronous.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from anappt.llm.models import ModelRole
from anappt.llm.provider import AnaPPTLLM


class ToolCall(BaseModel):
    """Represents a single tool call requested by the LLM.

    Attributes:
        id: Tool call identifier from the LLM.
        name: Name of the tool to call.
        arguments: JSON string of tool arguments.
    """

    id: str = ""
    name: str = ""
    arguments: str = "{}"


class ToolResult(BaseModel):
    """Represents the result of executing a tool.

    Attributes:
        name: Name of the tool that was called.
        result: The tool's output (string).
        error: Error message if the tool failed, empty otherwise.
    """

    name: str = ""
    result: str = ""
    error: str = ""


class ToolDef(BaseModel):
    """Definition of a tool available to the agent loop.

    Attributes:
        name: Tool name (must match the function name in the tools dict).
        description: Human-readable description of what the tool does.
        parameters: JSON schema dict describing the tool's parameters.
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class AgentLoop:
    """Tool-calling agent loop that iterates until a final answer is produced.

    The loop sends messages to the LLM, parses tool calls from the response,
    executes the requested tools, and feeds results back to the LLM.
    This continues until the LLM returns a response without tool calls
    or the max iteration limit is reached.

    Attributes:
        llm: The LLM provider.
        role: Model role to use for completions.
        tools: Dictionary mapping tool names to callable functions.
        tool_defs: List of ToolDef schemas for the LLM.
        max_iterations: Maximum number of tool-calling iterations.
    """

    def __init__(
        self,
        llm: AnaPPTLLM,
        role: ModelRole,
        tools: dict[str, Any] | None = None,
        tool_defs: list[ToolDef] | None = None,
        max_iterations: int = 10,
    ) -> None:
        """Initialize the agent loop.

        Args:
            llm: LLM provider instance.
            role: Model role to use ('reasoning', 'analysis', 'writing').
            tools: Dict mapping tool names to callable functions.
            tool_defs: List of tool definitions with schemas for the LLM.
            max_iterations: Max tool-calling iterations before giving up.
        """
        self.llm: AnaPPTLLM = llm
        self.role: ModelRole = role
        self.tools: dict[str, Any] = tools or {}
        self.tool_defs: list[ToolDef] = tool_defs or []
        self.max_iterations: int = max_iterations

    def _build_tool_schemas(self) -> list[dict[str, Any]]:
        """Build OpenAI-compatible tool schemas for the LLM.

        Returns:
            List of tool schema dicts in OpenAI function calling format.
        """
        schemas: list[dict[str, Any]] = []
        for td in self.tool_defs:
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": td.name,
                        "description": td.description,
                        "parameters": td.parameters or {"type": "object", "properties": {}},
                    },
                }
            )
        return schemas

    def _execute_tool(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call.

        Args:
            call: The tool call to execute.

        Returns:
            ToolResult with the tool's output or an error message.
        """
        func = self.tools.get(call.name)
        if func is None:
            return ToolResult(name=call.name, error=f"Unknown tool: {call.name}")

        try:
            arguments = json.loads(call.arguments) if call.arguments else {}
        except json.JSONDecodeError:
            arguments = {}

        try:
            result = func(**arguments)
            return ToolResult(name=call.name, result=str(result))
        except Exception as e:
            return ToolResult(name=call.name, error=str(e))

    def _parse_tool_calls(self, response: dict[str, Any]) -> list[ToolCall]:
        """Parse tool calls from the LLM response.

        Args:
            response: Response dict from AnaPPTLLM.chat_with_tools().

        Returns:
            List of ToolCall objects. Empty if no tool calls.
        """
        calls: list[ToolCall] = []
        for tc in response.get("tool_calls", []):
            calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=tc.get("name", ""),
                    arguments=tc.get("arguments", "{}"),
                )
            )
        return calls

    def run(
        self,
        system_prompt: str,
        user_message: str,
        extra_context: str = "",
    ) -> str:
        """Run the agent loop until a final answer is produced.

        Args:
            system_prompt: System prompt defining the agent's role and rules.
            user_message: The user's initial message/query.
            extra_context: Additional context to prepend to the user message.

        Returns:
            The final text answer from the LLM.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Build initial user message with context
        user_content = user_message
        if extra_context:
            user_content = f"{extra_context}\n\n{user_message}"
        messages.append({"role": "user", "content": user_content})

        # If no tools, do a simple chat
        if not self.tools or not self.tool_defs:
            return self.llm.chat(self.role, messages)

        tool_schemas = self._build_tool_schemas()

        for iteration in range(self.max_iterations):
            response = self.llm.chat_with_tools(self.role, messages, tool_schemas)

            # Check if LLM returned a final answer (no tool calls)
            tool_calls = self._parse_tool_calls(response)
            content = response.get("content", "")

            if not tool_calls:
                return content

            # Add assistant message with tool calls
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            messages.append(assistant_msg)

            # Execute each tool call and add results
            for call in tool_calls:
                result = self._execute_tool(call)
                tool_result_str = result.error if result.error else result.result
                messages.append(
                    {
                        "role": "tool",
                        "content": tool_result_str,
                        "tool_call_id": call.id,
                        "name": call.name,
                    }
                )

        # Max iterations reached — return last content or a message
        return self.llm.chat(self.role, messages)

    def run_simple(self, system_prompt: str, user_message: str) -> str:
        """Run a simple (no-tools) chat completion.

        Args:
            system_prompt: System prompt.
            user_message: User message.

        Returns:
            The LLM's response text.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self.llm.chat(self.role, messages)
