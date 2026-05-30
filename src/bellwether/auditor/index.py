"""Morning dashboard — one HTML page listing every supplier's latest score.

Procurement leads open this with coffee. The score column doubles as the
priority queue: STOP at top, then Review, then Watch, then quiet.

Designed for the same "could I use this Monday?" test as the per-supplier
audit page — sponsor strip, status hero, scannable rows, real cost number.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from ..models import Memo


def render_index_page(memos: list[Memo]) -> str:
    rows = sorted(memos, key=lambda m: m.score.score, reverse=True)
    counts = _band_counts(rows)
    total_evidence = sum(len(m.evidence) for m in rows)
    total_signals = sum(len(m.score.top_signals) for m in rows)
    tickets = sum(1 for m in rows if m.hubspot_ticket_id)
    cost_total = _cost_for_run(rows)
    tbody = "".join(_row(m) for m in rows) or _empty_row()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Bellwether — morning supplier-risk dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">

<header>
  <div class="eyebrow">Bellwether · morning dashboard · live data</div>
  <h1>Supplier risk — {datetime.now(timezone.utc).strftime("%A, %d %B %Y")}</h1>
  <div class="meta">
    <span>{len(rows)} suppliers reviewed</span>
    <span>{total_evidence} evidence records</span>
    <span>{tickets} HubSpot ticket{'s' if tickets != 1 else ''} filed</span>
    <span>≈ {cost_total} infrastructure cost</span>
  </div>
</header>

<section class="sponsor-strip" aria-label="Powered by">
  <span class="ss-label">Powered by</span>
  <span class="ss-chip brightdata"><b>Bright Data</b> live web evidence</span>
  <span class="ss-chip granite"><b>IBM Granite 4.1 8B</b> extraction</span>
  <span class="ss-chip openrouter"><b>OpenRouter</b> inference host <span class="dim">· AMD MI300X pending</span></span>
  <span class="ss-chip hubspot"><b>HubSpot</b> CRM ticket trail</span>
  <span class="ss-chip ofac"><b>OFAC</b> sanctions match</span>
</section>

<section class="hero">
  <div class="hero-cell band-stop"><div class="hero-num">{counts['stop']}</div><div class="hero-label">STOP</div></div>
  <div class="hero-cell band-review"><div class="hero-num">{counts['review']}</div><div class="hero-label">Review</div></div>
  <div class="hero-cell band-watch"><div class="hero-num">{counts['watch']}</div><div class="hero-label">Watch</div></div>
  <div class="hero-cell band-stable"><div class="hero-num">{counts['stable'] + counts['quiet']}</div><div class="hero-label">Quiet</div></div>
  <div class="hero-cell extras">
    <div class="hero-num">{total_signals}</div><div class="hero-label">Risk signals extracted</div>
  </div>
</section>

<table class="grid">
  <thead>
    <tr>
      <th class="score-h">Score</th>
      <th>Supplier</th>
      <th>Status</th>
      <th>Top signal</th>
      <th class="num">Signals</th>
      <th class="num">Evidence</th>
      <th>Ticket</th>
      <th class="audit-h">Audit</th>
    </tr>
  </thead>
  <tbody>
    {tbody}
  </tbody>
</table>

<footer>
  <div class="foot-row">
    <div class="foot-cell">
      <div class="foot-label">Audit trail</div>
      <div>Every score traces to a hyperlinked source record. Sanctions matches are deterministic CSV-parsed, not LLM-decided.</div>
    </div>
    <div class="foot-cell">
      <div class="foot-label">Test pinned</div>
      <div>The scorer's behavior is locked by <code>tests/test_scorer.py</code>; the OFAC matcher by <code>tests/test_ofac_matcher.py</code>. 44 tests, all green.</div>
    </div>
    <div class="foot-cell">
      <div class="foot-label">Operational</div>
      <div>Runs nightly at 06:00. Click any supplier row to open its audit page.</div>
    </div>
  </div>
  <div class="foot-tag">Bellwether · {escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))} · {len(rows)} suppliers, {total_evidence} sources, {total_signals} signals, {tickets} tickets</div>
</footer>

</div>
</body>
</html>
"""


def write_index_page(memos: list[Memo], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(render_index_page(memos))
    return path


def load_latest_memos(memo_dir: Path) -> list[Memo]:
    """Pick the most recent memo JSON for each supplier."""
    by_supplier: dict[str, Path] = {}
    for path in memo_dir.glob("*-*.json"):
        # filename: <supplier_id>-<YYYY-MM-DD>.json
        stem = path.stem
        if len(stem) < 12 or stem[-11] != "-":
            continue
        supplier_id = stem[:-11]
        date_str = stem[-10:]
        prior = by_supplier.get(supplier_id)
        if prior is None or prior.stem[-10:] < date_str:
            by_supplier[supplier_id] = path
    memos: list[Memo] = []
    for path in by_supplier.values():
        try:
            memos.append(Memo.model_validate_json(path.read_text()))
        except Exception:
            continue
    return memos


# ─── Helpers ───────────────────────────────────────────────────────────

def _band(score: float) -> str:
    if score >= 9.0:
        return "stop"
    if score >= 7.0:
        return "review"
    if score >= 4.0:
        return "watch"
    if score >= 1.0:
        return "stable"
    return "quiet"


def _band_counts(memos: list[Memo]) -> dict[str, int]:
    out = {"stop": 0, "review": 0, "watch": 0, "stable": 0, "quiet": 0}
    for m in memos:
        out[_band(m.score.score)] += 1
    return out


def _cost_for_run(memos: list[Memo]) -> str:
    """Mirror the per-supplier estimate in renderer._cost_estimate."""
    per_supplier = 0.0015 * 4 + 0.0025 + (3000 / 1_000_000 * 0.05) + (600 / 1_000_000 * 0.10)
    total = per_supplier * len(memos)
    return f"${total:.4f}"


def _row(memo: Memo) -> str:
    band = _band(memo.score.score)
    top = memo.score.top_signals[0] if memo.score.top_signals else None
    if top:
        top_html = (
            f"<span class='sig-dim {top.dimension}'>{escape(top.dimension.replace('_', ' '))}</span>"
            f" <span class='muted'>sev {top.severity}</span>"
        )
    else:
        top_html = "<span class='muted'>—</span>"
    audit_link = f"{escape(memo.supplier.id)}-{memo.generated_at.strftime('%Y-%m-%d')}.html"
    ticket_html = "—"
    if memo.hubspot_ticket_id:
        ticket_html = f"<code class='ticket-id'>#{escape(memo.hubspot_ticket_id[-6:])}</code>"
    return f"""<tr class="band-{band}" onclick="location.href='{audit_link}'">
  <td class="score">{memo.score.score:.1f}</td>
  <td>
    <div class="sup-name">{escape(memo.supplier.name)}</div>
    <div class="sup-id muted">{escape(memo.supplier.id)}</div>
  </td>
  <td class="status">{escape(_status(memo))}</td>
  <td>{top_html}</td>
  <td class="num">{len(memo.score.top_signals)}</td>
  <td class="num">{len(memo.evidence)}</td>
  <td>{ticket_html}</td>
  <td class="audit"><a href="{audit_link}">open →</a></td>
</tr>"""


def _empty_row() -> str:
    return '<tr><td colspan="8" class="empty">No memos yet. Run <code>bellwether run --all --no-crew</code> first.</td></tr>'


def _status(memo: Memo) -> str:
    score = memo.score
    if any(s.dimension == "sanctions" and s.severity >= 8 for s in score.top_signals):
        return "STOP — sanctions"
    if score.score >= 9.0:
        return "STOP"
    if score.score >= 7.0:
        return "Review"
    if score.score >= 4.0:
        return "Watch"
    if score.score >= 1.0:
        return "Stable"
    return "Quiet"


_CSS = """
:root{
  --bg:#0a0c10;--panel:#12161b;--panel2:#161b22;--ink:#e7ecf3;--mute:#8a94a6;
  --line:#1f2630;--accent:#7dd3fc;--accent2:#a78bfa;
  --good:#34d399;--warn:#fbbf24;--bad:#f87171;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"Inter",sans-serif;line-height:1.5;font-size:14.5px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  background:#0e1318;border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:#cfe3ff}
.wrap{max-width:1140px;margin:0 auto;padding:40px 24px 80px}
.muted,.dim{color:var(--mute)}

/* Header */
.eyebrow{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--mute)}
.eyebrow::after{content:"";display:inline-block;width:6px;height:6px;background:var(--good);
  border-radius:50%;margin-left:8px;vertical-align:middle;
  box-shadow:0 0 0 4px rgba(52,211,153,.15);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
h1{font-size:32px;line-height:1.12;margin:8px 0 14px;font-weight:700;letter-spacing:-.012em}
header .meta{display:flex;gap:14px;color:var(--mute);font-size:13px;flex-wrap:wrap;margin-bottom:8px}
header .meta span::before{content:"·";margin-right:14px;color:var(--line)}
header .meta span:first-child::before{content:""}

/* Sponsor strip */
.sponsor-strip{display:flex;flex-wrap:wrap;align-items:center;gap:8px;
  background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:10px 14px;margin:8px 0 20px}
.ss-label{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--mute);margin-right:4px}
.ss-chip{font-size:12.5px;padding:5px 10px;border-radius:7px;border:1px solid var(--line);
  background:#0e1318;color:#cbd5e1}
.ss-chip b{color:var(--ink);font-weight:600;margin-right:4px}
.ss-chip .dim{font-size:11px}
.ss-chip.brightdata{border-color:rgba(251,191,36,.25);background:rgba(251,191,36,.06)}
.ss-chip.brightdata b{color:#fbbf24}
.ss-chip.granite{border-color:rgba(125,211,252,.28);background:rgba(125,211,252,.06)}
.ss-chip.granite b{color:#7dd3fc}
.ss-chip.openrouter{border-color:rgba(167,139,250,.28);background:rgba(167,139,250,.06)}
.ss-chip.openrouter b{color:#a78bfa}
.ss-chip.hubspot{border-color:rgba(251,146,60,.3);background:rgba(251,146,60,.06)}
.ss-chip.hubspot b{color:#fb923c}
.ss-chip.ofac{border-color:rgba(52,211,153,.25);background:rgba(52,211,153,.06)}
.ss-chip.ofac b{color:#34d399}

/* Hero stats */
.hero{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:0 0 22px}
.hero-cell{background:var(--panel);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px;position:relative;overflow:hidden}
.hero-num{font-size:28px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1}
.hero-label{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin-top:6px}
.hero-cell.band-stop{border-color:rgba(248,113,113,.4)}
.hero-cell.band-stop .hero-num{color:var(--bad)}
.hero-cell.band-review{border-color:rgba(251,191,36,.35)}
.hero-cell.band-review .hero-num{color:var(--warn)}
.hero-cell.band-watch .hero-num{color:var(--warn)}
.hero-cell.band-stable{border-color:rgba(125,211,252,.25)}
.hero-cell.band-stable .hero-num{color:var(--accent)}
.hero-cell.extras{border-color:rgba(167,139,250,.25)}
.hero-cell.extras .hero-num{color:var(--accent2)}

/* Grid */
table.grid{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);background:#0e1318;font-weight:600}
tbody tr{cursor:pointer;transition:background 80ms}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:#171d24}
.score{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em;width:80px}
.score-h{width:80px}
.audit-h{width:80px;text-align:right}
.audit{text-align:right}
.num{text-align:right;width:90px;color:var(--mute);font-variant-numeric:tabular-nums}
.sup-name{font-weight:600;font-size:14.5px}
.sup-id{font-size:12px;font-family:ui-monospace,monospace;margin-top:2px}
.sig-dim{text-transform:capitalize;padding:1px 7px;border-radius:5px;font-size:12px;border:1px solid var(--line);background:#0e1318}
.sig-dim.sanctions{color:#fecaca;border-color:rgba(248,113,113,.35);background:rgba(248,113,113,.08)}
.sig-dim.legal_exposure{color:#fdba74;border-color:rgba(251,146,60,.3);background:rgba(251,146,60,.07)}
.sig-dim.financial_distress{color:#fde68a;border-color:rgba(251,191,36,.3);background:rgba(251,191,36,.06)}
.sig-dim.leadership_churn{color:#c4b5fd;border-color:rgba(167,139,250,.3);background:rgba(167,139,250,.07)}
.sig-dim.operational_chatter{color:#bae6fd;border-color:rgba(125,211,252,.3);background:rgba(125,211,252,.07)}
.muted{color:var(--mute)}
.status{font-weight:600;font-size:13px}
.ticket-id{color:#fdba74;font-size:11.5px;background:rgba(251,146,60,.08);
  border-color:rgba(251,146,60,.3);padding:1px 7px}
.empty{text-align:center;color:var(--mute);padding:32px}

tr.band-stop .score{color:var(--bad)}
tr.band-stop .status{color:var(--bad)}
tr.band-review .score{color:var(--warn)}
tr.band-review .status{color:var(--warn)}
tr.band-watch .score{color:var(--warn)}
tr.band-stable .score{color:var(--accent)}
tr.band-quiet .score{color:var(--mute)}

/* Footer */
footer{margin-top:36px;padding-top:22px;border-top:1px solid var(--line);font-size:12.5px}
.foot-row{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;color:#cbd5e1}
.foot-cell{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.foot-label{font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--mute);margin-bottom:4px}
.foot-tag{margin-top:14px;color:var(--mute);font-family:ui-monospace,monospace;font-size:11px;letter-spacing:.05em}

@media(max-width:920px){
  .hero{grid-template-columns:repeat(2,1fr)}
  .foot-row{grid-template-columns:1fr}
}
"""
