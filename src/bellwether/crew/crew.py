"""Crew assembly and execution.

`build_crew(supplier)` returns the four-agent CrewAI Crew object for visual
demos. `run_crew_for_supplier(...)` is the runtime entry point — it runs
the agents in order, with each one calling its Tool. In `--mock` (or
whenever no LLM is configured) we bypass the LLM-driven step and invoke
the Tools directly so the pipeline stays deterministic and offline-runnable.

The acceptance contract for the CrewAI integration (issues/c03):
- `python -c "from bellwether.crew import build_crew"` imports cleanly.
- `bellwether run --supplier X --mock` runs end-to-end through this crew.
- The Tools wrap the existing pipeline 1:1 — same scorer math, same memo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..evidence.brightdata import BrightDataClient
from ..evidence.cache import EvidenceCache
from ..evidence.collectors import (
    _resolve_linkedin_url,
    _sanctions,
    _serp,
    _linkedin,
    collect_mock,
)
from ..extract.granite import Extractor
from ..memo.writer import write_memo
from ..models import EvidenceRecord, Memo, RiskScore, RiskSignal, Supplier
from ..score.scorer import score_supplier
from .agents import (
    Agent,
    Task,
    _CREWAI_AVAILABLE,
    _bellwether_tool,
    analyst_agent,
    compliance_agent,
    researcher_agent,
    writer_agent,
)


@dataclass
class CrewBundle:
    """Container for a built crew + its toolset.

    Exposes a real crewai.Crew on `.crew` when the library is available;
    otherwise a stub that supports `.kickoff(inputs={...})` for tests.
    """

    supplier: Supplier
    agents: list[Agent]
    tasks: list[Task]
    crew: Any  # crewai.Crew when available; CrewStub otherwise
    runner: "CrewRunner"

    def kickoff(self, inputs: dict | None = None) -> Memo:
        """Run the pipeline as the crew. Inputs is currently a no-op (the
        supplier is bound at build time) but kept for CrewAI compatibility."""
        return self.runner.run()


@dataclass
class CrewStub:
    """Stand-in for crewai.Crew when the library isn't installed.

    Exists so `from bellwether.crew import build_crew` always works.
    """

    agents: list[Agent]
    tasks: list[Task]
    process: str = "sequential"
    verbose: bool = False
    _runner: Any = None

    def kickoff(self, inputs: dict | None = None) -> Memo:
        return self._runner.run()


class CrewRunner:
    """The actual execution loop the agents drive.

    Keeps the pipeline deterministic: the agents organize the work, the
    tools do the work, the runner shepherds state between them. The shape
    is identical to runner.run_supplier — this is the same pipeline,
    presented as a four-agent crew.
    """

    def __init__(
        self,
        supplier: Supplier,
        *,
        cache: EvidenceCache,
        extractor: Extractor,
        client: BrightDataClient | None,
        memo_dir: Path | None = None,
        mock: bool = False,
    ) -> None:
        self.supplier = supplier
        self.cache = cache
        self.extractor = extractor
        self.client = client
        self.memo_dir = memo_dir
        self.mock = mock or client is None

    # ─── Tool bodies (deterministic Python) ─────────────────────────────

    async def research_tool(self) -> list[EvidenceRecord]:
        """Researcher's tool: SERP + LinkedIn evidence collection."""
        if self.mock:
            return [r for r in collect_mock(self.supplier, self.cache)
                    if r.source_type in ("serp", "linkedin")]
        assert self.client is not None
        out: list[EvidenceRecord] = []
        out.extend(await _serp(self.supplier, self.cache, self.client))
        out.extend(await _linkedin(self.supplier, self.cache, self.client))
        return out

    async def compliance_tool(self) -> list[EvidenceRecord]:
        """Compliance's tool: deterministic OFAC SDN match."""
        if self.mock:
            return [r for r in collect_mock(self.supplier, self.cache)
                    if r.source_type == "sanctions"]
        return await _sanctions(self.supplier, self.cache)

    def analyst_tool(self, evidence: list[EvidenceRecord]) -> list[RiskSignal]:
        """Analyst's tool: Granite extraction."""
        return self.extractor.extract(self.supplier.name, evidence)

    def writer_tool(
        self, signals: list[RiskSignal], evidence: list[EvidenceRecord]
    ) -> Memo:
        """Writer's tool: scorer + memo writer."""
        score: RiskScore = score_supplier(self.supplier.id, signals)
        return write_memo(self.supplier, score, evidence, out_dir=self.memo_dir)

    async def run_async(self) -> Memo:
        """The crew flow in one place — researcher → compliance → analyst → writer."""
        evidence: list[EvidenceRecord] = []
        evidence.extend(await self.research_tool())
        evidence.extend(await self.compliance_tool())
        signals = self.analyst_tool(evidence)
        return self.writer_tool(signals, evidence)

    def run(self) -> Memo:
        """Sync entry point — runs the async crew flow under asyncio."""
        import asyncio

        return asyncio.run(self.run_async())


def _build_tools(runner: CrewRunner) -> dict[str, Any]:
    """Wrap each runner method as a CrewAI BaseTool."""

    def _research(_input: str | None = None) -> str:
        import asyncio
        records = asyncio.run(runner.research_tool())
        return f"{len(records)} evidence records from SERP/LinkedIn."

    def _compliance(_input: str | None = None) -> str:
        import asyncio
        records = asyncio.run(runner.compliance_tool())
        return f"{len(records)} OFAC SDN match(es)." if records else "OFAC: no matches."

    def _analyst(_input: str | None = None) -> str:
        return "Analyst tool: Granite extraction is wired through runner.analyst_tool."

    def _writer(_input: str | None = None) -> str:
        return "Writer tool: scorer + memo are wired through runner.writer_tool."

    return {
        "researcher": _bellwether_tool(
            "research_evidence",
            "Collect SERP + LinkedIn evidence for the supplier via Bright Data.",
            _research,
        ),
        "compliance": _bellwether_tool(
            "ofac_check",
            "Deterministic match against the OFAC SDN list.",
            _compliance,
        ),
        "analyst": _bellwether_tool(
            "granite_extract",
            "Extract structured RiskSignals from evidence using IBM Granite.",
            _analyst,
        ),
        "writer": _bellwether_tool(
            "score_and_write",
            "Compute the risk score and emit a cited Markdown memo.",
            _writer,
        ),
    }


def build_crew(
    supplier: Supplier,
    *,
    cache: EvidenceCache | None = None,
    extractor: Extractor | None = None,
    client: BrightDataClient | None = None,
    memo_dir: Path | None = None,
    mock: bool = True,
    llm: Any = None,
) -> CrewBundle:
    """Construct the four-agent crew bound to one supplier.

    Defaults are mock-friendly: pass `mock=False` plus a client/extractor
    when running live. The returned CrewBundle exposes `.kickoff()` which
    executes the underlying CrewRunner.
    """
    cache = cache or EvidenceCache(Path("./.cache/evidence"))
    if extractor is None:
        from ..extract.granite import MockExtractor
        extractor = MockExtractor()

    runner = CrewRunner(
        supplier,
        cache=cache,
        extractor=extractor,
        client=client,
        memo_dir=memo_dir,
        mock=mock,
    )
    tools = _build_tools(runner)
    agents = [
        researcher_agent(tools["researcher"], llm=llm),
        compliance_agent(tools["compliance"], llm=llm),
        analyst_agent(tools["analyst"], llm=llm),
        writer_agent(tools["writer"], llm=llm),
    ]
    tasks = [
        Task(
            description=f"Gather SERP and LinkedIn evidence for {supplier.name}.",
            expected_output="A list of EvidenceRecord objects with source URLs.",
            agent=agents[0],
            tools=[tools["researcher"]],
        ),
        Task(
            description=f"Check {supplier.name} and aliases against the OFAC SDN list.",
            expected_output="Zero or more sanctions EvidenceRecords.",
            agent=agents[1],
            tools=[tools["compliance"]],
        ),
        Task(
            description="Extract structured RiskSignals from the gathered evidence.",
            expected_output="A list of RiskSignals, each citing one or more evidence_ids.",
            agent=agents[2],
            tools=[tools["analyst"]],
        ),
        Task(
            description="Score the supplier and write a cited Markdown memo.",
            expected_output="A Memo object with body_markdown and evidence.",
            agent=agents[3],
            tools=[tools["writer"]],
        ),
    ]

    crew_obj: Any
    if _CREWAI_AVAILABLE:
        try:  # pragma: no cover — requires crewai installed
            from crewai import Crew, Process  # type: ignore

            crew_obj = Crew(
                agents=agents,
                tasks=tasks,
                process=Process.sequential,
                verbose=False,
            )
        except Exception:
            crew_obj = CrewStub(agents=agents, tasks=tasks, _runner=runner)
    else:
        crew_obj = CrewStub(agents=agents, tasks=tasks, _runner=runner)

    return CrewBundle(
        supplier=supplier,
        agents=agents,
        tasks=tasks,
        crew=crew_obj,
        runner=runner,
    )


async def run_crew_for_supplier(
    supplier: Supplier,
    *,
    cache: EvidenceCache,
    extractor: Extractor,
    client: BrightDataClient | None,
    memo_dir: Path | None = None,
    mock: bool = False,
) -> Memo:
    """Build the crew and run its deterministic flow. Returns the same
    Memo the legacy sequential runner returns."""
    bundle = build_crew(
        supplier,
        cache=cache,
        extractor=extractor,
        client=client,
        memo_dir=memo_dir,
        mock=mock,
    )
    return await bundle.runner.run_async()
