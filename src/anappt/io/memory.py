"""Project memory manager for AnaPPTAgent.

Maintains ``.anappt/memory.md`` — a persistent, LLM-curated record of
project progress, key decisions, important context, and data findings.

The memory is updated at conversation-exit time: the LLM is asked to
decide whether the just-completed session produced anything worth
remembering. If yes, it emits the full updated ``memory.md`` content
(preserving timestamps, appending new dated entries); if no, it emits
the literal token ``NO_UPDATE`` and the file is left untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from anappt.llm.models import ModelRole
from anappt.llm.provider import AnaPPTLLM

# Sentinel string the LLM emits when nothing in the session warrants a
# memory update. Matched case-insensitively after stripping whitespace.
_NO_UPDATE_TOKEN = "NO_UPDATE"

# System prompt for the memory-update LLM call. Hard-coded Chinese per
# the spec ("LLM 系统提示文案可硬编码中文常量").
_MEMORY_SYSTEM_PROMPT = (
    "你是项目记忆维护者。给定当前记忆与会话内容,判断是否有需要记入的项目进展/"
    "关键点/重要信息/数据进展。\n"
    "若有,输出更新后的完整 memory.md 内容(保留已有时间戳,追加新条目带日期 "
    "YYYY-MM-DD)。\n"
    "若本次无实质进展,仅输出字样 \"NO_UPDATE\"(不含其它字符)。\n"
    "记忆应简洁、信息密集,避免冗余复述对话本身。"
)


class MemoryManager:
    """Read and LLM-curated update of ``.anappt/memory.md``.

    The memory file is intentionally tolerant of absence: a fresh project
    starts with an empty ``memory.md``, and ``read()`` returns ``""`` in
    that case so callers can always treat the result as a plain string.
    """

    def __init__(self, memory_file: str | Path) -> None:
        """Initialize the memory manager.

        Args:
            memory_file: Path to ``memory.md`` (typically
                ``project_dir/.anappt/memory.md``). The file need not
                exist yet; ``read()`` returns ``""`` in that case.
        """
        self.memory_file: Path = Path(memory_file)

    def read(self) -> str:
        """Return the full text of ``memory.md``.

        Returns:
            The file's full contents, or an empty string if the file
            does not exist (or cannot be decoded).
        """
        if not self.memory_file.exists():
            return ""
        try:
            return self.memory_file.read_text(encoding="utf-8")
        except OSError:
            return ""

    def update(self, llm: AnaPPTLLM, role: ModelRole, session_content: str) -> bool:
        """Ask the LLM whether the session warrants a memory update.

        The current memory text and the just-finished session content
        are sent to the LLM. If the LLM returns the literal token
        ``NO_UPDATE`` (or empty/whitespace), the file is left untouched
        and ``False`` is returned. Otherwise the LLM's response is
        written verbatim to ``memory.md`` and ``True`` is returned.

        Args:
            llm: The LLM provider used for the update decision.
            role: Model role to invoke (typically ``reasoning``).
            session_content: Plain-text representation of the session
                (e.g. from :meth:`SessionLogger.get_full_text`).

        Returns:
            ``True`` if the memory file was updated, ``False`` otherwise.
        """
        current_memory = self.read()
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        user_prompt = (
            f"当前日期: {today}\n\n"
            f"=== 当前 memory.md ===\n{current_memory}\n\n"
            f"=== 本次会话内容 ===\n{session_content}\n\n"
            "请按系统提示规则输出更新后的完整 memory.md 内容,或 \"NO_UPDATE\"。"
        )

        messages = [
            {"role": "system", "content": _MEMORY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response = llm.chat(role, messages)
        # Be defensive: the LLM provider may return None on edge cases.
        response = (response or "").strip()

        if not response:
            return False
        if response.upper() == _NO_UPDATE_TOKEN:
            return False

        # Write the updated memory, ensuring the parent directory exists.
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(response, encoding="utf-8")
        return True

    def append(self, entry: str) -> bool:
        """向 ``memory.md`` 末尾增量追加一条带日期前缀的记忆条目。

        与 :meth:`update` 的区别在于:``update`` 会让 LLM 对整个
        ``memory.md`` 做全量重写(决定是否更新、保留已有时间戳并追加
        新条目);而本方法不调用 LLM,直接做一次纯文件的增量追加——
        读取现有内容,在末尾(若文件非空则先加一个空行分隔)写入
        ``## YYYY-MM-DD`` 标题行,再跟 ``entry`` 正文。日期使用 UTC,
        与 :meth:`update` 中 ``datetime.now(UTC)`` 的取值保持一致。

        对 ``entry`` 会先做 ``.strip()`` 处理;若 strip 后为空,则视为
        无实质内容,跳过写入并返回 ``False``(不写仅含日期标题的空条目,
        以避免给记忆文件引入噪音)。

        文件不存在时自动创建,父目录自动 ``mkdir(parents=True,
        exist_ok=True)``。读写均使用 UTF-8 编码。对 ``OSError`` 等异常
        做防御:出错时返回 ``False`` 而不抛出,与 :meth:`read` 的容错
        风格一致。

        Args:
            entry: 待追加的记忆条目正文(纯文本)。会先 strip,若 strip
                后为空则跳过本次追加。

        Returns:
            ``True`` 表示成功追加;``False`` 表示 ``entry`` strip 后为
            空或读写过程中发生 ``OSError``。
        """
        entry = (entry or "").strip()
        if not entry:
            return False

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        block = f"## {today}\n{entry}"

        try:
            current = self.read()
            # 文件非空时,在已有内容与新条目之间加一个空行分隔。
            content = f"{current}\n\n{block}" if current else block
            self.memory_file.parent.mkdir(parents=True, exist_ok=True)
            self.memory_file.write_text(content, encoding="utf-8")
        except OSError:
            return False
        return True
