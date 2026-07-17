"""Tests for AgentLoop tool-calling module."""

from __future__ import annotations

from unittest.mock import MagicMock

from anappt.tools.agent_loop import AgentLoop, ToolCall, ToolDef, ToolResult


class TestToolCall:
    """Tests for ToolCall model."""

    def test_defaults(self) -> None:
        tc = ToolCall()
        assert tc.id == ""
        assert tc.name == ""
        assert tc.arguments == "{}"

    def test_with_values(self) -> None:
        tc = ToolCall(id="call_1", name="search", arguments='{"query": "test"}')
        assert tc.id == "call_1"
        assert tc.name == "search"
        assert tc.arguments == '{"query": "test"}'


class TestToolResult:
    """Tests for ToolResult model."""

    def test_defaults(self) -> None:
        tr = ToolResult()
        assert tr.name == ""
        assert tr.result == ""
        assert tr.error == ""

    def test_with_result(self) -> None:
        tr = ToolResult(name="search", result="Found 3 results")
        assert tr.name == "search"
        assert tr.result == "Found 3 results"
        assert tr.error == ""

    def test_with_error(self) -> None:
        tr = ToolResult(name="search", error="API key missing")
        assert tr.error == "API key missing"
        assert tr.result == ""


class TestToolDef:
    """Tests for ToolDef model."""

    def test_defaults(self) -> None:
        td = ToolDef()
        assert td.name == ""
        assert td.description == ""
        assert td.parameters == {}

    def test_with_values(self) -> None:
        td = ToolDef(
            name="search_web",
            description="Search the web",
            parameters={"type": "object", "properties": {}},
        )
        assert td.name == "search_web"
        assert td.description == "Search the web"


class TestAgentLoopInit:
    """Tests for AgentLoop initialization."""

    def test_basic_init(self) -> None:
        llm = MagicMock()
        loop = AgentLoop(llm=llm, role="analysis")
        assert loop.llm is llm
        assert loop.role == "analysis"
        assert loop.tools == {}
        assert loop.tool_defs == []
        assert loop.max_iterations == 10

    def test_with_tools(self) -> None:
        llm = MagicMock()
        tools = {"echo": lambda x: x}
        tool_defs = [ToolDef(name="echo", description="Echo")]
        loop = AgentLoop(llm=llm, role="analysis", tools=tools, tool_defs=tool_defs)
        assert "echo" in loop.tools
        assert len(loop.tool_defs) == 1

    def test_custom_max_iterations(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="reasoning", max_iterations=5)
        assert loop.max_iterations == 5


class TestAgentLoopBuildToolSchemas:
    """Tests for _build_tool_schemas method."""

    def test_empty(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="analysis")
        assert loop._build_tool_schemas() == []

    def test_with_defs(self) -> None:
        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tool_defs=[
                ToolDef(
                    name="search",
                    description="Search",
                    parameters={"type": "object", "properties": {"q": {"type": "string"}}},
                )
            ],
        )
        schemas = loop._build_tool_schemas()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "search"
        assert schemas[0]["function"]["description"] == "Search"

    def test_empty_parameters(self) -> None:
        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tool_defs=[ToolDef(name="noop", description="No params", parameters={})],
        )
        schemas = loop._build_tool_schemas()
        assert schemas[0]["function"]["parameters"] == {"type": "object", "properties": {}}


class TestAgentLoopExecuteTool:
    """Tests for _execute_tool method."""

    def test_successful_execution(self) -> None:
        def add(a: int, b: int) -> int:
            return a + b

        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tools={"add": add},
        )
        call = ToolCall(name="add", arguments='{"a": 1, "b": 2}')
        result = loop._execute_tool(call)
        assert result.name == "add"
        assert result.result == "3"
        assert result.error == ""

    def test_unknown_tool(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="analysis")
        call = ToolCall(name="nonexistent", arguments="{}")
        result = loop._execute_tool(call)
        assert result.error == "Unknown tool: nonexistent"
        assert result.result == ""

    def test_tool_raises_exception(self) -> None:
        def failing_tool() -> None:
            raise ValueError("Boom!")

        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tools={"fail": failing_tool},
        )
        call = ToolCall(name="fail", arguments="{}")
        result = loop._execute_tool(call)
        assert "Boom!" in result.error

    def test_invalid_json_arguments(self) -> None:
        def echo(msg: str = "default") -> str:
            return msg

        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tools={"echo": echo},
        )
        call = ToolCall(name="echo", arguments="not valid json")
        result = loop._execute_tool(call)
        # Should handle gracefully (empty args, using default)
        assert result.error == ""

    def test_empty_arguments(self) -> None:
        def get_time() -> str:
            return "12:00"

        loop = AgentLoop(
            llm=MagicMock(),
            role="analysis",
            tools={"get_time": get_time},
        )
        call = ToolCall(name="get_time", arguments="")
        result = loop._execute_tool(call)
        assert result.result == "12:00"


class TestAgentLoopParseToolCalls:
    """Tests for _parse_tool_calls method."""

    def test_no_tool_calls(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="analysis")
        response = {"content": "Final answer", "tool_calls": []}
        calls = loop._parse_tool_calls(response)
        assert calls == []

    def test_with_tool_calls(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="analysis")
        response = {
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "search", "arguments": '{"q": "test"}'},
                {"id": "call_2", "name": "fetch", "arguments": '{"url": "http://example.com"}'},
            ],
        }
        calls = loop._parse_tool_calls(response)
        assert len(calls) == 2
        assert calls[0].name == "search"
        assert calls[1].name == "fetch"

    def test_missing_tool_calls_key(self) -> None:
        loop = AgentLoop(llm=MagicMock(), role="analysis")
        response = {"content": "answer"}
        calls = loop._parse_tool_calls(response)
        assert calls == []


class TestAgentLoopRun:
    """Tests for the run method."""

    def test_no_tools_simple_chat(self) -> None:
        """When no tools, should use simple chat."""
        llm = MagicMock()
        llm.chat.return_value = "Final answer"
        loop = AgentLoop(llm=llm, role="analysis")
        result = loop.run("You are helpful", "What is 2+2?")
        assert result == "Final answer"
        llm.chat.assert_called_once()
        # Verify messages structure
        call_args = llm.chat.call_args
        # chat(role, messages) — messages is second positional arg
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 1:
            messages = call_args.args[1]
        else:
            messages = call_args.args[0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_with_tools_returns_final_answer(self) -> None:
        """LLM calls a tool then returns final answer."""
        llm = MagicMock()

        # First call: LLM requests tool call
        # Second call: LLM returns final answer
        first_response = {
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "echo", "arguments": '{"msg": "hello"}'}
            ],
        }

        llm.chat_with_tools.return_value = first_response
        llm.chat.return_value = "The answer is hello"

        def echo(msg: str) -> str:
            return msg

        loop = AgentLoop(
            llm=llm,
            role="analysis",
            tools={"echo": echo},
            tool_defs=[ToolDef(name="echo", description="Echo a message")],
        )

        result = loop.run("System prompt", "Echo hello")
        # After tool call, loop should call llm.chat for final answer
        # (since second response has no tool_calls, but chat_with_tools returns first_response)
        # Actually, the loop calls chat_with_tools in the loop, and when no tool_calls,
        # returns content directly. But since we mocked chat_with_tools to always return
        # first_response, the loop will keep calling tools until max_iterations.
        # Then it falls back to llm.chat.
        # Let's verify the result
        assert result == "The answer is hello"

    def test_max_iterations_reached(self) -> None:
        """When LLM keeps calling tools, eventually returns chat response."""
        llm = MagicMock()
        llm.chat_with_tools.return_value = {
            "content": "",
            "tool_calls": [{"id": "1", "name": "echo", "arguments": "{}"}],
        }
        llm.chat.return_value = "Final fallback answer"

        loop = AgentLoop(
            llm=llm,
            role="analysis",
            tools={"echo": lambda: "echoed"},
            tool_defs=[ToolDef(name="echo", description="Echo")],
            max_iterations=3,
        )

        result = loop.run("system", "user")
        assert result == "Final fallback answer"
        # Should have called chat_with_tools 3 times (max_iterations)
        assert llm.chat_with_tools.call_count == 3
        # Then called chat once for fallback
        llm.chat.assert_called_once()

    def test_extra_context_prepended(self) -> None:
        """Extra context should be prepended to user message."""
        llm = MagicMock()
        llm.chat.return_value = "Answer"
        loop = AgentLoop(llm=llm, role="reasoning")

        loop.run("system", "user question", extra_context="Extra context here")

        call_args = llm.chat.call_args
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 1:
            messages = call_args.args[1]
        else:
            messages = call_args.args[0]
        user_msg = messages[1]["content"]
        assert "Extra context here" in user_msg
        assert "user question" in user_msg


class TestAgentLoopRunSimple:
    """Tests for run_simple method."""

    def test_basic_chat(self) -> None:
        llm = MagicMock()
        llm.chat.return_value = "Simple response"
        loop = AgentLoop(llm=llm, role="writing")

        result = loop.run_simple("Be concise", "Write a summary")
        assert result == "Simple response"

        call_args = llm.chat.call_args
        if call_args.kwargs.get("messages"):
            messages = call_args.kwargs["messages"]
        elif len(call_args.args) > 1:
            messages = call_args.args[1]
        else:
            messages = call_args.args[0]
        assert len(messages) == 2
        assert messages[0]["content"] == "Be concise"
        assert messages[1]["content"] == "Write a summary"
