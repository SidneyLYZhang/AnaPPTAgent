"""Textual TUI application and adapter for AnaPPTAgent (Tasks 7-8).

Provides :class:`ReportBuilderApp` — a textual-based terminal application
that renders a structured conversation layout (header / chat log /
thinking bar / input area / footer) and bridges the synchronous
:class:`anappt.conversation.ConversationRunner` to the async textual
event loop via a worker thread + input queue.

:class:`TextualUIAdapter` implements both
:class:`anappt.types.InteractiveUIProtocol` and
:class:`anappt.types.StreamingSink`: chat messages and thinking-bar
updates are forwarded to the widgets via ``call_from_thread``, while
``input`` blocks on a ``queue.Queue`` that is fed by the input area's
Enter handler.

The CLI (``anappt run`` / ``resume`` / ``interactive``) constructs a
``runner_factory`` closure that wires the adapter as both ``ui`` and
``stream_sink`` for the :class:`ConversationRunner`, then starts the
textual app.
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from enum import Enum
from itertools import cycle
from typing import TYPE_CHECKING, Any

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, RichLog, Static, TextArea
from wcwidth import wcwidth

from anappt.i18n import t

if TYPE_CHECKING:
    from anappt.conversation import ConversationRunner

# Braille spinner cycle (10 frames), advanced once per tick.
SPINNER = cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")


def tail_by_width(s: str, max_width: int) -> str:
    """Return the trailing substring of ``s`` fitting within ``max_width``.

    Characters are counted by their display width via :func:`wcwidth.wcwidth`
    (CJK characters occupy 2 columns). The tail is built from the end of
    the string until adding the next character would exceed ``max_width``.

    Args:
        s: The input string.
        max_width: Maximum display width of the returned tail.

    Returns:
        The trailing substring whose display width is ``<= max_width``.
    """
    out: list[str] = []
    w = 0
    for ch in reversed(s):
        w += wcwidth(ch)
        if w > max_width:
            break
        out.append(ch)
    return "".join(reversed(out))


class AppState(Enum):
    """Visual state of the thinking bar.

    Attributes:
        IDLE: No stream in progress; the thinking bar is hidden.
        STREAMING: An LLM stream is active; the thinking bar shows the
            spinner and the tail of the current buffer.
    """

    IDLE = "idle"
    STREAMING = "streaming"


class InputArea(TextArea):
    """Multi-line text input that submits on Enter and breaks on Shift+Enter.

    Overrides TextArea's ``_on_key`` so that a plain ``enter`` key submits
    the current text to the app's input queue (via
    :meth:`ReportBuilderApp.submit_input`) instead of inserting a newline,
    while ``shift+enter`` inserts a newline (TextArea's default for
    ``enter``). All other keys fall through to TextArea's default handler.
    """

    async def _on_key(self, event: events.Key) -> None:
        """Intercept Enter/Shift+Enter; delegate the rest to TextArea.

        Args:
            event: The key event dispatched to this widget.
        """
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.app.submit_input()
            return
        if event.key == "shift+enter":
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        await super()._on_key(event)


class ReportBuilderApp(App):
    """Textual application driving the conversation TUI.

    Layout (top to bottom): :class:`Header` (stage progress title),
    :class:`RichLog` (chat history, flexible height),
    :class:`Static` (single-line thinking bar, hidden when idle),
    :class:`InputArea` (multi-line input, fixed height),
    :class:`Footer` (keybinding hints).

    The :class:`ConversationRunner` runs in a worker thread
    (``run_worker(..., thread=True)``) and communicates with the UI
    through :class:`TextualUIAdapter` + ``call_from_thread``. User input
    flows back via ``self._input_queue`` (a ``queue.Queue`` fed by
    :meth:`submit_input`).

    Attributes:
        runner_factory: Callable ``(adapter) -> ConversationRunner`` that
            wires the adapter as both ``ui`` and ``stream_sink``.
        welcome_message: Optional system line written to the chat area on
            mount (used by ``anappt interactive``).
        thinking_buf: Current thinking-bar buffer (set by the adapter).
        state: Current :class:`AppState` (IDLE or STREAMING).
        adapter: The :class:`TextualUIAdapter` instance (created on mount).
        runner: The :class:`ConversationRunner` instance (created on mount).
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    #chat {
        height: 1fr;
        border: solid $accent;
    }
    #thinking {
        height: 1;
    }
    #input {
        height: 5;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("pageup", "scroll_chat_up", "PgUp", show=False, priority=True),
        Binding("pagedown", "scroll_chat_down", "PgDn", show=False, priority=True),
    ]

    def __init__(
        self,
        runner_factory: Callable[[TextualUIAdapter], ConversationRunner | None],
        welcome_message: str | None = None,
    ) -> None:
        """Initialize the app.

        Args:
            runner_factory: Callback that receives the adapter and returns
                a ConversationRunner (or None for testing — the app exits
                immediately when the runner is None).
            welcome_message: Optional system message written to the chat
                area on mount before the runner starts.
        """
        super().__init__()
        self.runner_factory = runner_factory
        self.welcome_message = welcome_message
        self.thinking_buf = ""
        self.state = AppState.IDLE
        self._input_queue: queue.Queue[str] = queue.Queue()
        self.adapter: TextualUIAdapter | None = None
        self.runner: ConversationRunner | None = None

    def compose(self) -> ComposeResult:
        """Yield the widget tree: Header / chat / thinking / input / Footer."""
        yield Header()
        yield RichLog(id="chat", auto_scroll=True, markup=True)
        yield Static(id="thinking")
        yield InputArea(id="input", soft_wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        """Create the adapter + runner, start the thinking tick and worker."""
        self.adapter = TextualUIAdapter(self)
        self.runner = self.runner_factory(self.adapter)
        if self.welcome_message:
            self.adapter.print(self.welcome_message)
        self.refresh_title()
        self.set_interval(0.1, self.tick_thinking)
        self.run_worker(self._run_runner, thread=True)
        self.query_one("#input", InputArea).focus()

    def _run_runner(self) -> None:
        """Run the ConversationRunner in a worker thread; exit app on finish.

        When ``self.runner`` is None (testing), the app exits immediately.
        """
        if self.runner is None:
            self.exit()
            return
        try:
            self.runner.run()
        finally:
            self.exit()

    def refresh_title(self) -> None:
        """Update the header title with the current stage progress."""
        cur = None
        try:
            if self.runner is not None:
                cur = self.runner.ctx.state.get_current_stage()
        except Exception:
            cur = None
        if cur is None:
            self.title = t("tui.title_complete")
        else:
            step = cur.id.lstrip("S") or "0"
            self.title = t("tui.title", step=step, name=t(cur.name))

    def submit_input(self) -> None:
        """Submit the current input area text to the input queue.

        Reads the text from the ``#input`` widget, clears it, and puts the
        text on ``self._input_queue`` for the adapter's ``input`` method
        to consume.
        """
        ta = self.query_one("#input", InputArea)
        text = ta.text
        ta.text = ""
        self._input_queue.put(text)

    def tick_thinking(self) -> None:
        """Refresh the thinking bar (called every 100ms by set_interval).

        When ``state`` is ``STREAMING``, shows the spinner + tail of
        ``thinking_buf`` (or the idle placeholder when the buffer is
        empty). When ``IDLE``, hides the bar.
        """
        bar = self.query_one("#thinking", Static)
        if self.state != AppState.STREAMING:
            bar.update("")
            bar.display = False
            return
        bar.display = True
        spinner = next(SPINNER)
        if not self.thinking_buf:
            bar.update(
                f"[yellow]✦ 思考中 {spinner}[/] [dim]{t('conv.thinking_idle')}[/]"
            )
        else:
            tail = tail_by_width(self.thinking_buf, 40)
            bar.update(f"[yellow]✦ 思考中 {spinner}[/] [dim italic]…{tail}▍[/]")

    # --- Keybinding actions for PgUp/PgDn chat scrolling ------------------

    def action_scroll_chat_up(self) -> None:
        """Scroll the chat log up by one page (PgUp binding)."""
        self.query_one("#chat", RichLog).scroll_page_up()

    def action_scroll_chat_down(self) -> None:
        """Scroll the chat log down by one page (PgDn binding)."""
        self.query_one("#chat", RichLog).scroll_page_down()


class TextualUIAdapter:
    """Adapter bridging ConversationRunner to the textual UI.

    Implements :class:`anappt.types.InteractiveUIProtocol` (print/input/
    confirm/table/progress) and :class:`anappt.types.StreamingSink`
    (user_message/assistant_message/thinking_update/thinking_idle/
    thinking_clear). All widget mutations are scheduled on the textual
    main loop via ``app.call_from_thread``. ``input`` blocks on
    ``app._input_queue`` so the synchronous runner can wait for user
    input from the async UI.
    """

    def __init__(self, app: ReportBuilderApp) -> None:
        """Initialize the adapter.

        Args:
            app: The owning ReportBuilderApp instance.
        """
        self.app = app

    # ------------------------------------------------------------------
    # Thread-marshalling helper
    # ------------------------------------------------------------------

    def _call_on_main(self, callback: Callable[[], Any]) -> None:
        """Run ``callback`` on the textual main loop thread.

        When invoked from the worker thread (the normal case for adapter
        calls driven by :class:`ConversationRunner`), this delegates to
        ``app.call_from_thread``. When already on the main thread (e.g.
        the welcome message printed during ``on_mount``),
        ``call_from_thread`` would raise ``RuntimeError`` — so the
        callback is invoked directly instead. Updates are dropped when
        the app is no longer running (shutdown).
        """
        if not self.app.is_running:
            return
        if threading.get_ident() == self.app._thread_id:
            callback()
        else:
            self.app.call_from_thread(callback)

    # ------------------------------------------------------------------
    # InteractiveUIProtocol
    # ------------------------------------------------------------------

    def print(self, message: str) -> None:
        """Write a system line to the chat area (markup-escaped).

        Args:
            message: The system text to display.
        """
        from rich.markup import escape

        def _write() -> None:
            self.app.query_one("#chat", RichLog).write(escape(message))

        self._call_on_main(_write)

    def input(self, prompt: str) -> str | None:
        """Block until the user submits input, returning the text.

        Polls ``app._input_queue`` with a short timeout so the method can
        exit promptly when the app is shutting down (returns ``None``).

        Args:
            prompt: Unused in the TUI (input comes from the input area);
                kept for protocol compatibility.

        Returns:
            The submitted text, or ``None`` when the app has exited.
        """
        while True:
            try:
                return self.app._input_queue.get(timeout=0.2)
            except queue.Empty:
                if not self.app.is_running:
                    return None

    def confirm(self, prompt: str) -> bool:
        """Write the prompt to chat and wait for a y/yes response.

        Args:
            prompt: The confirmation prompt text.

        Returns:
            True if the user replied ``y`` or ``yes`` (case-insensitive).
        """
        self.print(f"{prompt} [y/N]")
        resp = self.input("")
        return (resp or "").strip().lower() in ("y", "yes")

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Render a table into the chat area using a rich Table.

        Args:
            headers: Column header strings.
            rows: List of row data, each row a list of cell strings.
        """
        from rich.markup import escape
        from rich.table import Table

        def _write() -> None:
            tbl = Table()
            for h in headers:
                tbl.add_column(escape(h))
            for r in rows:
                tbl.add_row(*[escape(str(c)) for c in r])
            self.app.query_one("#chat", RichLog).write(tbl)

        self._call_on_main(_write)

    def progress(self, message: str) -> None:
        """Show a progress/status message as a bracketed system line.

        Args:
            message: The progress message text.
        """
        self.print(f"[{message}]")

    # ------------------------------------------------------------------
    # StreamingSink
    # ------------------------------------------------------------------

    def user_message(self, text: str) -> None:
        """Render a user message into the chat area.

        Args:
            text: The user's submitted text.
        """
        from rich.markup import escape

        label = t("tui.user_label")

        def _write() -> None:
            self.app.query_one("#chat", RichLog).write(
                f"[bold cyan]{label}：[/]{escape(text)}"
            )

        self._call_on_main(_write)

    def assistant_message(self, text: str) -> None:
        """Render an assistant message into the chat area and refresh title.

        Args:
            text: The full accumulated assistant response text.
        """
        from rich.markup import escape

        label = t("tui.assistant_label")

        def _write() -> None:
            self.app.query_one("#chat", RichLog).write(
                f"[bold green]{label}：[/]{escape(text)}"
            )
            self.app.refresh_title()

        self._call_on_main(_write)

    def thinking_update(self, buf: str) -> None:
        """Update the thinking buffer and switch to STREAMING state.

        Args:
            buf: The current thinking buffer (reasoning or content).
        """
        self._call_on_main(lambda: self._do_thinking_update(buf))

    def _do_thinking_update(self, buf: str) -> None:
        """Main-thread side of thinking_update (sets buffer + state)."""
        self.app.thinking_buf = buf
        self.app.state = AppState.STREAMING

    def thinking_idle(self, msg: str) -> None:
        """Switch to STREAMING state with an empty buffer (idle placeholder).

        Args:
            msg: The idle placeholder message (unused — the tick renders
                ``conv.thinking_idle`` when the buffer is empty).
        """
        self._call_on_main(lambda: self._do_thinking_idle(msg))

    def _do_thinking_idle(self, msg: str) -> None:
        """Main-thread side of thinking_idle (clears buffer, sets state)."""
        _ = msg  # placeholder text is rendered by tick_thinking
        self.app.thinking_buf = ""
        self.app.state = AppState.STREAMING

    def thinking_clear(self) -> None:
        """Clear the thinking buffer and switch back to IDLE state."""
        self._call_on_main(self._do_thinking_clear)

    def _do_thinking_clear(self) -> None:
        """Main-thread side of thinking_clear (clears buffer + state)."""
        self.app.thinking_buf = ""
        self.app.state = AppState.IDLE


__all__ = [
    "AppState",
    "InputArea",
    "ReportBuilderApp",
    "SPINNER",
    "TextualUIAdapter",
    "tail_by_width",
]
