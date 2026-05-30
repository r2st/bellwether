"""Bellwether CLI — `bellwether <command>` after `pip install -e .`."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import config as cfg
from . import health as health_mod
from .auditor import load_latest_memos, write_audit_page, write_index_page
from .comet import CometError, CometUnavailable, file_ticket_via_comet
from .evidence.brightdata import BrightDataClient
from .evidence.cache import EvidenceCache
from .extract.granite import GraniteExtractor, MockExtractor
from .fixtures import load_suppliers
from .fixtures.loader import get_supplier
from .hubspot import HubSpotClient, HubSpotError
from .models import Memo
from .runner import run_supplier

app = typer.Typer(help="Bellwether — supplier risk counter-intel agent.", no_args_is_help=True)
console = Console()


def _cache() -> EvidenceCache:
    return EvidenceCache(Path(cfg.EVIDENCE_CACHE_DIR))


def _memo_dir() -> Path:
    return Path(cfg.MEMO_OUTPUT_DIR)


def _bd_client_or_none(mock: bool) -> BrightDataClient | None:
    if mock:
        return None
    if not cfg.BRIGHTDATA_API_TOKEN:
        console.print(
            "[yellow]No BRIGHTDATA_API_TOKEN set; falling back to --mock. "
            "Run `bellwether verify` and fill in keys/.env to enable live mode.[/yellow]"
        )
        return None
    return BrightDataClient(
        api_token=cfg.BRIGHTDATA_API_TOKEN,
        serp_zone=cfg.BRIGHTDATA_SERP_ZONE,
        unlocker_zone=cfg.BRIGHTDATA_WEB_UNLOCKER_ZONE,
        linkedin_dataset_id=cfg.BRIGHTDATA_LINKEDIN_DATASET_ID,
    )


def _extractor(mock: bool):
    url = cfg.AMD_INFERENCE_URL
    if mock or not url or "REPLACE_ME" in url:
        if not mock and url:
            console.print(
                "[yellow]AMD_INFERENCE_URL is a placeholder; using MockExtractor.[/yellow]"
            )
        return MockExtractor()
    return GraniteExtractor(
        base_url=url,
        model=cfg.AMD_INFERENCE_MODEL,
        api_key=cfg.AMD_DEVCLOUD_API_KEY or "dummy",
    )


@app.command()
def run(
    supplier_id: str = typer.Option(None, "--supplier", "-s", help="Run one supplier by id."),
    all_suppliers: bool = typer.Option(False, "--all", help="Run the full demo list."),
    mock: bool = typer.Option(False, "--mock", help="Use fixtures + rule extractor (no tokens needed)."),
    file_ticket: bool = typer.Option(False, "--file-ticket", help="File a Supplier Review ticket in HubSpot."),
    via_comet: bool = typer.Option(
        False,
        "--via-comet",
        help="Drive HubSpot in-browser via Perplexity Comet; falls back to REST.",
    ),
    via_crew: bool = typer.Option(
        True,
        "--via-crew/--no-crew",
        help="Orchestrate through the CrewAI four-agent crew (default) or the linear pipeline.",
    ),
) -> None:
    """Collect evidence, extract signals, score, and write a memo."""
    if not supplier_id and not all_suppliers:
        raise typer.BadParameter("Pass --supplier <id> or --all.")

    asyncio.run(_run_async(supplier_id, all_suppliers, mock, file_ticket, via_comet, via_crew))


async def _run_async(
    supplier_id: str | None,
    all_suppliers: bool,
    mock: bool,
    file_ticket: bool,
    via_comet: bool,
    via_crew: bool,
) -> None:
    cache = _cache()
    client = _bd_client_or_none(mock)
    extractor = _extractor(mock)
    memo_dir = _memo_dir()
    hs = _hubspot_or_none(file_ticket)

    suppliers = load_suppliers() if all_suppliers else [_resolve(supplier_id)]

    try:
        for s in suppliers:
            console.rule(f"[bold]{s.name}[/bold] ({s.id})")
            memo = await run_supplier(
                s,
                cache=cache,
                extractor=extractor,
                client=client,
                memo_dir=memo_dir,
                mock=mock,
                via_crew=via_crew,
            )
            html_path = write_audit_page(memo, memo_dir)
            ticket_id, comet_screenshot = _file_ticket(hs, s, memo, via_comet)
            _print_summary(memo, html_path, ticket_id, comet_screenshot)
    finally:
        if client is not None:
            await client.aclose()
        if hs is not None:
            hs.close()


def _hubspot_or_none(file_ticket: bool) -> HubSpotClient | None:
    if not file_ticket:
        return None
    if not cfg.HUBSPOT_PRIVATE_APP_TOKEN:
        console.print(
            "[yellow]No HUBSPOT_PRIVATE_APP_TOKEN set; skipping ticket filing.[/yellow]"
        )
        return None
    return HubSpotClient(cfg.HUBSPOT_PRIVATE_APP_TOKEN)


def _file_ticket(
    hs: HubSpotClient | None,
    supplier,
    memo,
    via_comet: bool,
) -> tuple[str | None, Path | None]:
    """Try Comet first if requested; fall back to REST; return (ticket_id, screenshot)."""
    if hs is None and not via_comet:
        return None, None
    if not supplier.hubspot_id:
        console.print(
            f"[yellow]  ! {supplier.id}: no hubspot_id, skipping ticket[/yellow]"
        )
        return None, None

    screenshot: Path | None = None
    if via_comet:
        try:
            screenshot = file_ticket_via_comet(memo, supplier, out_dir=_memo_dir())
            console.print(
                f"[green]  ✓ Comet filed the ticket; screenshot at {screenshot}[/green]"
            )
            return None, screenshot
        except CometUnavailable as e:
            console.print(
                f"[yellow]  Comet not available ({e}); falling back to REST.[/yellow]"
            )
        except CometError as e:
            console.print(
                f"[yellow]  Comet flow failed ({e}); falling back to REST.[/yellow]"
            )

    if hs is None:
        return None, screenshot
    try:
        return (
            hs.file_supplier_review_ticket(supplier, memo, memo_dir=_memo_dir()),
            screenshot,
        )
    except HubSpotError as e:
        console.print(f"[red]  ! HubSpot ticket failed: {e}[/red]")
        return None, screenshot


def _resolve(supplier_id: str | None):
    if not supplier_id:
        raise typer.BadParameter("--supplier is required when not using --all")
    s = get_supplier(supplier_id)
    if s is None:
        raise typer.BadParameter(
            f"Unknown supplier {supplier_id!r}. Try `bellwether suppliers` to list them."
        )
    return s


def _print_summary(
    memo,
    html_path: Path | None = None,
    ticket_id: str | None = None,
    comet_screenshot: Path | None = None,
) -> None:
    score = memo.score
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_row("Score", f"[bold]{score.score:.1f}[/bold] / 10")
    table.add_row("Signals", str(len(score.top_signals)))
    table.add_row("Evidence", f"{len(memo.evidence)} records")
    if html_path:
        table.add_row("Audit page", f"[dim]{html_path}[/dim]")
    if ticket_id:
        table.add_row("HubSpot ticket", f"[green]{ticket_id}[/green]")
    if comet_screenshot:
        table.add_row("Comet screenshot", f"[green]{comet_screenshot}[/green]")
    console.print(table)
    for sig in score.top_signals:
        console.print(
            f"  · [cyan]{sig.dimension}[/cyan] "
            f"[yellow]sev {sig.severity}[/yellow] — {sig.description}"
        )
    console.print()


@app.command()
def suppliers() -> None:
    """List demo suppliers."""
    table = Table(title="Demo suppliers")
    table.add_column("id")
    table.add_column("name")
    table.add_column("domain")
    for s in load_suppliers():
        table.add_row(s.id, s.name, s.domain or "")
    console.print(table)


@app.command()
def view(
    supplier_id: str = typer.Argument(None, help="Supplier id (omit with --index for the dashboard)."),
    index: bool = typer.Option(False, "--index", help="Open the morning dashboard listing every supplier."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Open the page in your default browser."),
) -> None:
    """Open the most recent audit HTML for a supplier, or the morning dashboard with --index."""
    import webbrowser

    memo_dir = _memo_dir()
    if index:
        memos = load_latest_memos(memo_dir)
        path = write_index_page(memos, memo_dir)
        console.print(f"[green]Wrote[/green] {path} ({len(memos)} suppliers)")
        if open_browser:
            webbrowser.open(path.resolve().as_uri())
        return

    if not supplier_id:
        raise typer.BadParameter("Pass a supplier id, or use --index for the dashboard.")
    candidates = sorted(memo_dir.glob(f"{supplier_id}-*.json"), reverse=True)
    if not candidates:
        raise typer.BadParameter(
            f"No memo found for {supplier_id!r} in {memo_dir}. "
            f"Run `bellwether run --supplier {supplier_id} --mock` first."
        )
    memo = Memo.model_validate_json(candidates[0].read_text())
    html_path = write_audit_page(memo, memo_dir)
    console.print(f"[green]Wrote[/green] {html_path}")
    if open_browser:
        webbrowser.open(html_path.resolve().as_uri())


@app.command()
def ping() -> None:
    """Check connectivity to every configured provider — Bright Data, AMD/Granite, HubSpot, OFAC, HF."""
    table = Table(title="Provider health", show_lines=False)
    table.add_column("provider")
    table.add_column("status")
    table.add_column("detail")
    any_red = False
    for check in health_mod.run_all():
        if check.ok:
            table.add_row(check.name, "[green]OK[/green]", check.detail)
        else:
            any_red = True
            table.add_row(check.name, "[red]FAIL[/red]", check.detail)
    console.print(table)
    if any_red:
        console.print("[yellow]\nSome providers are not reachable. Pipeline will still run in --mock mode.[/yellow]")
        sys.exit(1)


@app.command()
def verify() -> None:
    """Check that all required tokens are set in ../keys/.env."""
    sys.exit(0 if cfg.verify() else 1)


if __name__ == "__main__":
    app()
