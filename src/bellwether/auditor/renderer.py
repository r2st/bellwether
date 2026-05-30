"""Render a Memo as a self-contained HTML audit page.

The output is one file — no JS, no external CSS, no runtime calls.
Every signal score is hyperlinked to the exact EvidenceRecord that
produced it. This is the artifact a procurement auditor reviews when
they want to convince themselves the number is real.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from ..models import EvidenceRecord, Memo, RiskSignal


def render_audit_page(memo: Memo) -> str:
    score = memo.score
    by_id = {r.id: r for r in memo.evidence}
    cited_ids = _cited_ids(score.top_signals)
    cited = [by_id[i] for i in cited_ids if i in by_id]
    uncited = [r for r in memo.evidence if r.id not in cited_ids]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{escape(memo.supplier.name)} — Bellwether audit</title>
<style>{_CSS}</style>
</head>
<body>
<div class="wrap">
{_header(memo)}
{_score_block(memo)}
{_signals_block(score.top_signals, by_id)}
{_evidence_block("Cited evidence", cited, highlight=True)}
{_evidence_block("Other evidence collected (not cited in top signals)", uncited)}
{_footer(memo)}
</div>
</body>
</html>
"""


def write_audit_page(memo: Memo, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = memo.generated_at.strftime("%Y-%m-%d")
    path = out_dir / f"{memo.supplier.id}-{date}.html"
    path.write_text(render_audit_page(memo))
    return path


def _cited_ids(signals: list[RiskSignal]) -> list[str]:
    out: list[str] = []
    for s in signals:
        for eid in s.evidence_ids:
            if eid not in out:
                out.append(eid)
    return out


def _header(memo: Memo) -> str:
    s = memo.supplier
    return f"""<header>
  <div class="eyebrow">Bellwether · supplier risk audit</div>
  <h1>{escape(s.name)}</h1>
  <div class="meta">
    <span>{escape(s.id)}</span>
    {('<span>' + escape(s.domain) + '</span>') if s.domain else ''}
    <span>generated {escape(memo.generated_at.strftime("%Y-%m-%d %H:%M UTC"))}</span>
  </div>
</header>"""


def _score_block(memo: Memo) -> str:
    score = memo.score
    delta_html = ""
    if score.score_delta_7d is not None:
        sign = "+" if score.score_delta_7d >= 0 else ""
        cls = "up" if score.score_delta_7d > 0 else "down"
        delta_html = f'<span class="delta {cls}">{sign}{score.score_delta_7d:.1f} vs last week</span>'
    headline = _headline(memo)
    band = _band_class(score.score)
    return f"""<section class="score-block band-{band}">
  <div class="score-big">{score.score:.1f}<span class="oo10">/10</span></div>
  <div class="score-meta">
    <div class="headline">{escape(headline)}</div>
    <div class="sub">{len(score.top_signals)} signals · {len(memo.evidence)} evidence records {delta_html}</div>
  </div>
</section>"""


def _signals_block(signals: list[RiskSignal], by_id: dict[str, EvidenceRecord]) -> str:
    if not signals:
        return '<section><h2>Top signals</h2><p class="muted">No material signals this week.</p></section>'
    rows = []
    for i, sig in enumerate(signals, 1):
        bar_w = int(round(sig.severity * 10))  # 0-100
        bar = f'<div class="bar"><div class="bar-fill sev-{sig.severity}" style="width:{bar_w}%"></div></div>'
        cites = " ".join(
            f'<a class="cite" href="#ev-{escape(eid)}">[{escape(eid[:8])}]</a>'
            for eid in sig.evidence_ids
        )
        rows.append(f"""<li class="sig">
  <div class="sig-head">
    <span class="sig-num">{i}</span>
    <span class="sig-dim">{escape(sig.dimension.replace('_', ' '))}</span>
    <span class="sig-sev">severity {sig.severity}/10</span>
    <span class="sig-conf">confidence {int(sig.confidence*100)}%</span>
  </div>
  {bar}
  <p class="sig-desc">{escape(sig.description)} {cites}</p>
</li>""")
    return f'<section><h2>Top signals</h2><ol class="signals">{"".join(rows)}</ol></section>'


def _evidence_block(title: str, records: list[EvidenceRecord], highlight: bool = False) -> str:
    if not records:
        return ""
    rows = []
    for r in records:
        cls = "ev highlighted" if highlight else "ev"
        title_html = escape(r.title or r.source_url)
        published = ""
        if r.published_at:
            published = f'<span class="ev-date">published {r.published_at.strftime("%Y-%m-%d")}</span>'
        rows.append(f"""<li class="{cls}" id="ev-{escape(r.id)}">
  <div class="ev-head">
    <code class="ev-id">{escape(r.id)}</code>
    <span class="ev-src">{escape(r.source_type)}</span>
    {published}
  </div>
  <a class="ev-title" href="{escape(r.source_url)}" target="_blank" rel="noopener">{title_html}</a>
  <p class="ev-snip">{escape(r.snippet)}</p>
  <div class="ev-meta">
    fetched {escape(r.fetched_at.strftime("%Y-%m-%d %H:%M UTC"))}
    · scraper <code>{escape(r.scraper_id)}</code>
  </div>
</li>""")
    return f'<section><h2>{escape(title)}</h2><ul class="evidence">{"".join(rows)}</ul></section>'


def _footer(memo: Memo) -> str:
    return f"""<footer>
  <div>Audit produced by Bellwether · supplier {escape(memo.supplier.id)}</div>
  <div class="muted">Every score above is hyperlinked to the source record that produced it.
    Sanctions hits are determined by deterministic string match against the OFAC SDN list,
    not by the language model.</div>
</footer>"""


def _headline(memo: Memo) -> str:
    score = memo.score
    if any(s.dimension == "sanctions" and s.severity >= 8 for s in score.top_signals):
        return "STOP — sanctions hit"
    if any("bankruptcy" in s.description.lower() for s in score.top_signals):
        return "STOP — bankruptcy signal"
    if score.score >= 9.0:
        return "STOP — multiple high-severity signals stacked"
    if score.score >= 7.0:
        return "Review required — multiple material signals"
    if score.score >= 4.0:
        return "Watch — material signals present"
    if score.score >= 1.0:
        return "Stable — minor signals"
    return "Quiet — no change"


def _band_class(score: float) -> str:
    if score >= 9.0:
        return "stop"
    if score >= 7.0:
        return "review"
    if score >= 4.0:
        return "watch"
    if score >= 1.0:
        return "stable"
    return "quiet"


_CSS = """
:root{
  --bg:#0b0d10;--panel:#12161b;--panel2:#161b22;--ink:#e7ecf3;--mute:#8a94a6;
  --line:#1f2630;--accent:#7dd3fc;--accent2:#a78bfa;
  --good:#34d399;--warn:#fbbf24;--bad:#f87171;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"Inter",sans-serif;line-height:1.55;font-size:15px}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;
  background:#0e1318;border:1px solid var(--line);border-radius:5px;padding:1px 6px;color:#cfe3ff}
.wrap{max-width:920px;margin:0 auto;padding:40px 24px 80px}

header{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:24px}
.eyebrow{font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--mute)}
h1{font-size:34px;line-height:1.15;margin:8px 0 8px;font-weight:700;letter-spacing:-.01em}
.meta{display:flex;gap:14px;color:var(--mute);font-size:13px;flex-wrap:wrap}
.meta span::before{content:"·";margin-right:14px;color:var(--line)}
.meta span:first-child::before{content:""}

h2{font-size:18px;margin:36px 0 12px;letter-spacing:-.005em;padding-bottom:8px;border-bottom:1px solid var(--line)}
section{margin-top:8px}
.muted{color:var(--mute)}

.score-block{display:flex;gap:24px;align-items:center;padding:20px 22px;
  background:var(--panel);border:1px solid var(--line);border-radius:14px;margin:8px 0 4px}
.score-big{font-size:72px;font-weight:800;letter-spacing:-.03em;line-height:1}
.score-big .oo10{font-size:22px;color:var(--mute);font-weight:500;margin-left:6px}
.score-meta .headline{font-size:17px;font-weight:600;letter-spacing:-.005em}
.score-meta .sub{font-size:13px;color:var(--mute);margin-top:4px}
.delta{margin-left:12px;padding:2px 8px;border-radius:999px;font-size:11px;letter-spacing:.05em}
.delta.up{background:rgba(248,113,113,.12);color:var(--bad);border:1px solid rgba(248,113,113,.3)}
.delta.down{background:rgba(52,211,153,.12);color:var(--good);border:1px solid rgba(52,211,153,.3)}

.band-stop{border-color:rgba(248,113,113,.4)}
.band-stop .score-big{color:var(--bad)}
.band-review{border-color:rgba(251,191,36,.4)}
.band-review .score-big{color:var(--warn)}
.band-watch .score-big{color:var(--warn)}
.band-stable .score-big{color:var(--accent)}
.band-quiet .score-big{color:var(--mute)}

.signals{list-style:none;padding:0;margin:0;display:grid;gap:10px}
.sig{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.sig-head{display:flex;gap:10px;align-items:center;font-size:13px;color:var(--mute);flex-wrap:wrap}
.sig-num{width:22px;height:22px;border-radius:50%;background:var(--bg);border:1px solid var(--line);
  display:inline-flex;align-items:center;justify-content:center;color:var(--accent);font-weight:700;font-size:12px}
.sig-dim{color:var(--ink);font-weight:600;text-transform:capitalize}
.sig-sev,.sig-conf{font-size:12px}
.bar{height:6px;background:#0e1318;border-radius:999px;margin:8px 0 8px;overflow:hidden}
.bar-fill{height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:999px}
.bar-fill.sev-10,.bar-fill.sev-9,.bar-fill.sev-8{background:linear-gradient(90deg,var(--warn),var(--bad))}
.sig-desc{margin:0;font-size:14px}
.cite{font-size:12px;color:var(--accent);font-family:ui-monospace,monospace;margin-left:4px}

.evidence{list-style:none;padding:0;margin:0;display:grid;gap:10px}
.ev{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.ev.highlighted{border-color:rgba(125,211,252,.4);background:linear-gradient(180deg,rgba(125,211,252,.04),transparent 70%)}
.ev:target{border-color:var(--accent2);box-shadow:0 0 0 2px rgba(167,139,250,.25)}
.ev-head{display:flex;gap:10px;align-items:center;font-size:12px;color:var(--mute);flex-wrap:wrap}
.ev-id{color:var(--accent2)}
.ev-src{text-transform:uppercase;letter-spacing:.08em;font-size:11px}
.ev-title{display:block;font-weight:600;margin:6px 0 4px;font-size:14.5px}
.ev-snip{margin:0;font-size:13.5px;color:#cbd5e1}
.ev-meta{margin-top:8px;font-size:11.5px;color:var(--mute)}
.ev-meta code{font-size:11px}

footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--line);color:var(--mute);font-size:12.5px;display:grid;gap:6px}
"""
