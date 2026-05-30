"""Morning dashboard — one HTML page listing every supplier's latest score.

Procurement leads open this with coffee. The score column doubles as the
priority queue: STOP at top, then Review, then Watch, then quiet.
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
    tbody = "".join(_row(m) for m in rows) or _empty_row()
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Bellwether — supplier risk dashboard</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="eyebrow">Bellwether · morning dashboard</div>
  <h1>Supplier risk — {datetime.now(timezone.utc).strftime("%A %d %B %Y")}</h1>
  <div class="meta">
    <span>{len(rows)} suppliers reviewed</span>
    <span class="band-stop">{counts["stop"]} STOP</span>
    <span class="band-review">{counts["review"]} Review</span>
    <span class="band-watch">{counts["watch"]} Watch</span>
    <span class="muted">{counts["stable"] + counts["quiet"]} quiet</span>
  </div>
</header>

<table class="grid">
  <thead>
    <tr>
      <th class="score-h">Score</th>
      <th>Supplier</th>
      <th>Status</th>
      <th>Top signal</th>
      <th class="num">Signals</th>
      <th class="num">Evidence</th>
      <th class="audit-h">Audit</th>
    </tr>
  </thead>
  <tbody>
    {tbody}
  </tbody>
</table>

<footer>
  <div class="muted">Generated {escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}
    · click any row to open that supplier's audit page</div>
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
        # supplier_id is everything except the trailing date (10 chars + dash)
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


def _row(memo: Memo) -> str:
    band = _band(memo.score.score)
    top = memo.score.top_signals[0] if memo.score.top_signals else None
    top_html = (
        f"<span class='sig-dim'>{escape(top.dimension.replace('_', ' '))}</span> "
        f"<span class='muted'>sev {top.severity}</span>"
        if top else "<span class='muted'>—</span>"
    )
    audit_link = f"{escape(memo.supplier.id)}-{memo.generated_at.strftime('%Y-%m-%d')}.html"
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
  <td class="audit"><a href="{audit_link}">open →</a></td>
</tr>"""


def _empty_row() -> str:
    return '<tr><td colspan="7" class="empty">No memos yet. Run <code>bellwether run --all --mock</code> first.</td></tr>'


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
  --bg:#0b0d10;--panel:#12161b;--panel2:#161b22;--ink:#e7ecf3;--mute:#8a94a6;
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
.wrap{max-width:1100px;margin:0 auto;padding:40px 24px 80px}

.eyebrow{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--mute)}
h1{font-size:30px;line-height:1.15;margin:8px 0 14px;font-weight:700;letter-spacing:-.01em}
.meta{display:flex;gap:14px;color:var(--mute);font-size:13px;flex-wrap:wrap;margin-bottom:22px}
.meta span::before{content:"·";margin-right:14px;color:var(--line)}
.meta span:first-child::before{content:""}
.meta .band-stop{color:var(--bad)}
.meta .band-review{color:var(--warn)}
.meta .band-watch{color:var(--warn)}

table.grid{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--mute);background:#0e1318;font-weight:600}
tbody tr{cursor:pointer;transition:background 80ms}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover{background:#171d24}
.score{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.01em;width:80px}
.score-h{width:80px}
.audit-h{width:80px;text-align:right}
.audit{text-align:right}
.num{text-align:right;width:90px;color:var(--mute);font-variant-numeric:tabular-nums}
.sup-name{font-weight:600}
.sup-id{font-size:12px;font-family:ui-monospace,monospace;margin-top:2px}
.sig-dim{text-transform:capitalize}
.muted{color:var(--mute)}
.status{font-weight:600;font-size:13px}
.empty{text-align:center;color:var(--mute);padding:32px}

tr.band-stop .score{color:var(--bad)}
tr.band-stop .status{color:var(--bad)}
tr.band-review .score{color:var(--warn)}
tr.band-review .status{color:var(--warn)}
tr.band-watch .score{color:var(--warn)}
tr.band-stable .score{color:var(--accent)}
tr.band-quiet .score{color:var(--mute)}

footer{margin-top:32px;color:var(--mute);font-size:12.5px}
"""
