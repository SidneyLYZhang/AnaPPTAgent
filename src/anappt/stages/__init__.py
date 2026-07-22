"""Stages package — exports all six pipeline stage implementations.

Also exposes :func:`build_stage_registry`, the canonical stage-id →
StageBase instance map shared by the Orchestrator-based execution path
and the conversation-driven TUI (``ConversationRunner``). Centralizing
the registry here avoids drift between the two paths and lets
``ConversationRunner`` look up a stage by id without re-instantiating
the orchestrator.
"""

from __future__ import annotations

from anappt.stage_base import StageBase
from anappt.stages.s1_topic import S1TopicStage
from anappt.stages.s2_data_req import S2DataRequirementStage
from anappt.stages.s3_data_load import S3DataLoadStage
from anappt.stages.s4_analysis import S4AnalysisStage
from anappt.stages.s5_report import S5ReportStage
from anappt.stages.s6_ppt import S6PPTStage

__all__ = [
    "S1TopicStage",
    "S2DataRequirementStage",
    "S3DataLoadStage",
    "S4AnalysisStage",
    "S5ReportStage",
    "S6PPTStage",
    "build_stage_registry",
    "get_stage_class",
]


def build_stage_registry() -> dict[str, StageBase]:
    """Instantiate every pipeline stage and return an id→stage mapping.

    Returns:
        Dict mapping each stage id (``"S1"``..``"S6"``) to a fresh
        :class:`StageBase` subclass instance.
    """
    stages: list[StageBase] = [
        S1TopicStage(),
        S2DataRequirementStage(),
        S3DataLoadStage(),
        S4AnalysisStage(),
        S5ReportStage(),
        S6PPTStage(),
    ]
    return {s.stage_id: s for s in stages}


def get_stage_class(stage_id: str) -> type[StageBase] | None:
    """Return the stage class registered under ``stage_id``.

    Args:
        stage_id: Stage identifier (e.g. ``"S1"``).

    Returns:
        The StageBase subclass, or ``None`` when the id is unknown.
    """
    mapping: dict[str, type[StageBase]] = {
        "S1": S1TopicStage,
        "S2": S2DataRequirementStage,
        "S3": S3DataLoadStage,
        "S4": S4AnalysisStage,
        "S5": S5ReportStage,
        "S6": S6PPTStage,
    }
    return mapping.get(stage_id)
