"""Agent + Tool factories.

Each agent has one exclusive responsibility and one Tool. Tools are
deterministic Python wrappers around the existing pipeline modules so the
crew flow is reproducible and auditable.

Two import surfaces matter:
- `crewai` (Agent, Task, Crew, Tool) — for the LLM-driven path
- The Bellwether modules — for the deterministic tool bodies

If crewai is not installed (e.g. on a stripped-down dev box) we expose
minimal stand-ins for Agent/Task/Crew so `from bellwether.crew import
build_crew` still imports and the eager runner still works.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

try:  # crewai is a project dependency; keep an import-safe fallback for dev
    from crewai import Agent, Task  # type: ignore
    from crewai.tools import BaseTool  # type: ignore
    _CREWAI_AVAILABLE = True
except Exception:  # pragma: no cover — exercised only when the dep is absent
    _CREWAI_AVAILABLE = False

    @dataclass
    class Agent:  # type: ignore[no-redef]
        role: str
        goal: str
        backstory: str = ""
        tools: list[Any] = field(default_factory=list)
        allow_delegation: bool = False
        verbose: bool = False
        llm: Any = None

    @dataclass
    class Task:  # type: ignore[no-redef]
        description: str
        expected_output: str
        agent: Agent | None = None
        tools: list[Any] = field(default_factory=list)

    class BaseTool:  # type: ignore[no-redef]
        name: str = "tool"
        description: str = ""

        def _run(self, *args, **kwargs) -> Any:
            raise NotImplementedError


def _bellwether_tool(name: str, description: str, fn: Callable[..., Any]) -> BaseTool:
    """Wrap a plain callable as a CrewAI BaseTool with our naming convention.

    `_run` must live in the class body — CrewAI's BaseTool is abstract via
    ABC, and assigning `_run` *after* class creation doesn't update
    `__abstractmethods__`, so instantiation fails with TypeError.
    """
    _name, _desc, _fn = name, description, fn

    class _Tool(BaseTool):  # type: ignore[misc, valid-type]
        name: str = _name
        description: str = _desc

        def _run(self, *args, **kwargs):  # type: ignore[override]
            return _fn(*args, **kwargs)

    return _Tool()


def researcher_agent(tool: BaseTool, *, llm: Any = None) -> Agent:
    return Agent(
        role="Researcher",
        goal=(
            "Gather public-web evidence about the supplier from Google News "
            "SERP and the company's LinkedIn page via Bright Data. Return "
            "EvidenceRecord objects with source URLs preserved for citation."
        ),
        backstory=(
            "You read the open web for procurement teams. You never invent "
            "facts; every record must carry a source_url, fetched_at, and "
            "scraper_id."
        ),
        tools=[tool],
        allow_delegation=False,
        verbose=False,
        llm=llm,
    )


def compliance_agent(tool: BaseTool, *, llm: Any = None) -> Agent:
    return Agent(
        role="Compliance",
        goal=(
            "Check the supplier name and known aliases against the official "
            "OFAC SDN list. Match deterministically on parsed CSV — never "
            "via the LLM. Emit one EvidenceRecord per match, none if clean."
        ),
        backstory=(
            "Sanctions are a hard stop. You only describe matches; you do "
            "not decide them. The list is authoritative."
        ),
        tools=[tool],
        allow_delegation=False,
        verbose=False,
        llm=llm,
    )


def analyst_agent(tool: BaseTool, *, llm: Any = None) -> Agent:
    return Agent(
        role="Analyst",
        goal=(
            "Extract structured RiskSignal objects from gathered evidence "
            "using IBM Granite on AMD MI300X. Severities 0-10, every signal "
            "carries evidence_ids that trace back to source URLs."
        ),
        backstory=(
            "You are precise. Granite is your tool, not your reasoner — the "
            "schema is fixed, no marketing language, no hedging."
        ),
        tools=[tool],
        allow_delegation=False,
        verbose=False,
        llm=llm,
    )


def writer_agent(tool: BaseTool, *, llm: Any = None) -> Agent:
    return Agent(
        role="Writer",
        goal=(
            "Score the supplier deterministically and write a one-page "
            "Markdown memo with every score hyperlinked to its evidence."
        ),
        backstory=(
            "You are the auditor's friend. The scoring math is Python; the "
            "memo is your delivery format."
        ),
        tools=[tool],
        allow_delegation=False,
        verbose=False,
        llm=llm,
    )


__all__ = [
    "Agent",
    "Task",
    "BaseTool",
    "_CREWAI_AVAILABLE",
    "_bellwether_tool",
    "researcher_agent",
    "compliance_agent",
    "analyst_agent",
    "writer_agent",
]
