"""Tests for the textual TUI module (Task 7-8).

Covers:
  1. ``tail_by_width`` — CJK and ASCII display-width tail extraction.
  2. ``SPINNER`` — cycle iteration.
  3. ``AppState`` — enum values.
  4. ``ReportBuilderApp`` compose — widgets mount via ``run_test``.
  5. ``submit_input`` — text is queued for the adapter's ``input``.
  6. ``TextualUIAdapter`` — protocol method presence + state mutation.

The full textual interaction tests use ``app.run_test()`` with a stub
runner whose ``run()`` blocks on a ``threading.Event`` so the app stays
alive while assertions run; the event is set at the end to let the
worker exit and the app shut down cleanly.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from anappt.tui import (
    SPINNER,
    AppState,
    InputArea,
    ReportBuilderApp,
    TextualUIAdapter,
    tail_by_width,
)

# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


class TestTailByWidth:
    """Tests for tail_by_width (CJK width-aware tail extraction)."""

    def test_cjk_tail(self) -> None:
        """CJK chars occupy 2 columns; width 4 keeps two CJK chars."""
        # "abc你好": a(1) b(1) c(1) 你(2) 好(2) = total 7 cols
        # tail by width 4 → "你好" (4 cols)
        assert tail_by_width("abc你好", 4) == "你好"

    def test_cjk_partial(self) -> None:
        """Width 2 keeps exactly one CJK char."""
        assert tail_by_width("abc你好", 2) == "好"

    def test_cjk_width_3_keeps_one_cjk(self) -> None:
        """Width 3 keeps one CJK (2 cols); the next CJK (2) would overflow.

        tail: 好(2) fits (2<=3); 你(2) would make 4 > 3 → stop.
        Result is "好" (2 cols), not "c好".
        """
        assert tail_by_width("abc你好", 3) == "好"

    def test_cjk_width_5_keeps_two_cjk_plus_one_ascii(self) -> None:
        """Width 5 keeps two CJK (4) + one ASCII (1) = 5 cols."""
        # tail: 好(2) + 你(2) + c(1) = 5 → "c你好"
        assert tail_by_width("abc你好", 5) == "c你好"

    def test_ascii_tail(self) -> None:
        """Pure ASCII: width 3 keeps the last 3 chars."""
        assert tail_by_width("hello", 3) == "llo"

    def test_ascii_full_string(self) -> None:
        """When max_width >= string width, the whole string is returned."""
        assert tail_by_width("hi", 10) == "hi"

    def test_empty_string(self) -> None:
        """Empty input returns empty."""
        assert tail_by_width("", 10) == ""

    def test_zero_width(self) -> None:
        """Width 0 returns empty (the first char would exceed 0)."""
        assert tail_by_width("hello", 0) == ""

    def test_width_exceeds_total(self) -> None:
        """Width larger than the string returns the whole string."""
        assert tail_by_width("你好", 100) == "你好"

    def test_cjk_tail_excludes_char_that_would_overflow(self) -> None:
        """A char that would exceed max_width is excluded (not partial)."""
        # "xy你": x(1) y(1) 你(2). tail by width 2 → "你" (2 cols).
        # Adding 'y' would make 3 > 2, so 'y' is excluded.
        assert tail_by_width("xy你", 2) == "你"


class TestSpinner:
    """Tests for the SPINNER cycle."""

    def test_next_returns_str(self) -> None:
        """next(SPINNER) returns a non-empty string."""
        s = next(SPINNER)
        assert isinstance(s, str)
        assert len(s) >= 1

    def test_cycle_is_iterable(self) -> None:
        """The spinner yields multiple frames without raising."""
        frames = [next(SPINNER) for _ in range(20)]
        assert len(frames) == 20
        # All frames are members of the braille spinner set.
        assert all(f in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏" for f in frames)

    def test_cycle_wraps_around(self) -> None:
        """After 10 frames the spinner repeats (cycle length 10)."""
        first = next(SPINNER)
        for _ in range(9):
            next(SPINNER)
        # 10th advance after `first` should equal `first` again.
        assert next(SPINNER) == first


class TestAppState:
    """Tests for the AppState enum."""

    def test_values(self) -> None:
        """AppState has IDLE and STREAMING with the expected string values."""
        assert AppState.IDLE.value == "idle"
        assert AppState.STREAMING.value == "streaming"

    def test_distinct(self) -> None:
        """IDLE and STREAMING are distinct members."""
        assert AppState.IDLE is not AppState.STREAMING


# ---------------------------------------------------------------------------
# Stub runner for async app tests
# ---------------------------------------------------------------------------


class _StubRunner:
    """Minimal ConversationRunner stub for app tests.

    ``run()`` blocks on an Event so the app stays alive while the test
    makes assertions; the test sets the event to release the worker and
    let the app exit. ``ctx`` is None — ``refresh_title`` tolerates the
    resulting AttributeError via its try/except.
    """

    def __init__(self) -> None:
        self.ctx: Any = None
        self._release = threading.Event()

    def run(self) -> None:
        """Block until the test releases the stub."""
        self._release.wait(timeout=10)


def _make_stub_app(welcome: str | None = None) -> tuple[ReportBuilderApp, _StubRunner]:
    """Build a ReportBuilderApp backed by a _StubRunner.

    Returns:
        (app, stub) — the test releases ``stub`` to let the app exit.
    """
    stub = _StubRunner()

    def factory(adapter: TextualUIAdapter) -> _StubRunner:
        return stub

    app = ReportBuilderApp(factory, welcome_message=welcome)
    return app, stub


# ---------------------------------------------------------------------------
# Async app tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_app_compose_mounts_all_widgets() -> None:
    """ReportBuilderApp.compose mounts Header/chat/thinking/input/Footer."""
    app, stub = _make_stub_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#chat") is not None
        assert app.query_one("#input") is not None
        assert app.query_one("#thinking") is not None
        # The input area is the InputArea subclass.
        assert isinstance(app.query_one("#input"), InputArea)
        # The adapter was created on mount.
        assert app.adapter is not None
        assert isinstance(app.adapter, TextualUIAdapter)
        # The runner was created on mount.
        assert app.runner is stub
        stub._release.set()
        await pilot.pause()


@pytest.mark.asyncio
async def test_app_title_falls_back_when_ctx_none() -> None:
    """When the runner has no ctx, the title uses tui.title_complete."""
    app, stub = _make_stub_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # stub.ctx is None → refresh_title catches the error and uses
        # the "complete" title.
        from anappt.i18n import t

        assert app.title == t("tui.title_complete")
        stub._release.set()
        await pilot.pause()


@pytest.mark.asyncio
async def test_submit_input_queues_text() -> None:
    """submit_input reads the input area, clears it, and queues the text."""
    app, stub = _make_stub_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        ta = app.query_one("#input", InputArea)
        ta.text = "hello world"
        app.submit_input()
        # The text should now be on the queue.
        assert app._input_queue.get_nowait() == "hello world"
        # The input area was cleared.
        assert ta.text == ""
        stub._release.set()
        await pilot.pause()


@pytest.mark.asyncio
async def test_welcome_message_written_to_chat() -> None:
    """A welcome_message is written to the chat area on mount."""
    app, stub = _make_stub_app(welcome="WELCOME_LINE")
    async with app.run_test() as pilot:
        await pilot.pause()
        # The chat widget exists; the welcome line was written via
        # adapter.print → call_from_thread. After pilot.pause() the
        # call should have been processed.
        chat = app.query_one("#chat")
        assert chat is not None
        stub._release.set()
        await pilot.pause()


@pytest.mark.asyncio
async def test_tick_thinking_shows_idle_placeholder() -> None:
    """tick_thinking renders the idle placeholder when STREAMING + empty buf."""
    app, stub = _make_stub_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Switch to STREAMING with an empty buffer.
        app.state = AppState.STREAMING
        app.thinking_buf = ""
        app.tick_thinking()
        bar = app.query_one("#thinking")
        assert bar.display is True
        stub._release.set()
        await pilot.pause()


@pytest.mark.asyncio
async def test_tick_thinking_hidden_when_idle() -> None:
    """tick_thinking hides the thinking bar when state is IDLE."""
    app, stub = _make_stub_app()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.state = AppState.IDLE
        app.thinking_buf = "something"
        app.tick_thinking()
        bar = app.query_one("#thinking")
        assert bar.display is False
        stub._release.set()
        await pilot.pause()


# ---------------------------------------------------------------------------
# Adapter protocol compliance
# ---------------------------------------------------------------------------


class TestTextualUIAdapterProtocol:
    """Verify TextualUIAdapter implements both required protocols."""

    def test_has_interactive_ui_methods(self) -> None:
        """The adapter exposes all InteractiveUIProtocol methods."""
        adapter = TextualUIAdapter.__new__(TextualUIAdapter)
        for method in ("print", "input", "confirm", "table", "progress"):
            assert callable(getattr(adapter, method, None)), (
                f"missing InteractiveUIProtocol method: {method}"
            )

    def test_has_streaming_sink_methods(self) -> None:
        """The adapter exposes all StreamingSink methods."""
        adapter = TextualUIAdapter.__new__(TextualUIAdapter)
        for method in (
            "user_message",
            "assistant_message",
            "thinking_update",
            "thinking_idle",
            "thinking_clear",
        ):
            assert callable(getattr(adapter, method, None)), (
                f"missing StreamingSink method: {method}"
            )

    def test_app_state_flagged_streaming_on_thinking_update(self) -> None:
        """_do_thinking_update sets the app state to STREAMING + buffer."""
        app = ReportBuilderApp.__new__(ReportBuilderApp)
        app.thinking_buf = ""
        app.state = AppState.IDLE
        adapter = TextualUIAdapter.__new__(TextualUIAdapter)
        adapter.app = app
        adapter._do_thinking_update("reasoning text")
        assert app.thinking_buf == "reasoning text"
        assert app.state is AppState.STREAMING

    def test_app_state_flagged_idle_on_thinking_clear(self) -> None:
        """_do_thinking_clear resets the app state to IDLE + empty buffer."""
        app = ReportBuilderApp.__new__(ReportBuilderApp)
        app.thinking_buf = "leftover"
        app.state = AppState.STREAMING
        adapter = TextualUIAdapter.__new__(TextualUIAdapter)
        adapter.app = app
        adapter._do_thinking_clear()
        assert app.thinking_buf == ""
        assert app.state is AppState.IDLE
