# Bellwether

> A morning agent that watches your supplier list, surfaces operational and
> reputational risk from the live web, and files an audit-grade review ticket
> in your CRM — autonomously, with every claim cited.

**Hackathon:** Web Data UNLOCKED · lablab.ai (May 25–30, 2026), SF finale May 30–31.

The name *Bellwether* is what procurement teams call the supplier whose
behavior signals the herd. The product turns that idea inside out: a bellwether
*for* your suppliers, ringing the bell before a delivery slips.

---

## What it does

Every morning at 06:00 local, Bellwether:

1. Reads your supplier list out of HubSpot.
2. For each supplier, fans out a small CrewAI crew (researcher, watchman,
   compliance, writer) that queries the live web through Bright Data — SERP,
   LinkedIn, court records, sanctions lists.
3. Hands the evidence to an IBM Granite model hosted on AMD MI300X to extract
   structured risk signals.
4. Scores the supplier with deterministic Python (so the math is auditable),
   then writes a one-page memo with every score hyperlinked to its source.
5. Drives the CRM in-browser with Perplexity Comet to file a *Supplier Review*
   ticket and assign it to the account owner.

If a supplier is quiet, the memo is a one-line "no change." If a sanctions hit
lands, the ticket is opened at severity-1 within minutes of the source list
updating.

---

## The stack

| Layer            | Tool                            | Why it's here                         |
| ---------------- | ------------------------------- | ------------------------------------- |
| Live web data    | Bright Data (SERP, LinkedIn, Web Unlocker) | Fresh evidence, not stale DBs |
| Model hosting    | AMD MI300X + ROCm + vLLM        | Self-hosted Granite, no token-meter   |
| Extraction model | IBM Granite 3.1 8B Instruct     | Cheap, strong at JSON-mode extraction |
| Orchestration    | CrewAI                          | One crew per supplier, parallel fan-out |
| Last-mile action | Perplexity Comet                | Drives the CRM the way a human would  |
| Demo CRM         | HubSpot (free tier)             | Lowest-friction enterprise surface    |

Full architecture, day-by-day build plan, and the 6-minute demo script live in
[`../research/procurement-counter-intel.html`](../research/procurement-counter-intel.html).

---

## Layout

```
Bellwether/
├── README.md              ← this file
├── config.py              ← loads ../keys/.env, exposes typed constants
├── pyproject.toml         ← installable as `bellwether` (pip install -e .)
└── src/bellwether/
    ├── __init__.py
    ├── brightdata/        ← live web evidence collectors
    ├── extract/           ← Granite prompts + Pydantic signal schemas
    ├── score/             ← deterministic risk scorer
    ├── crew/              ← CrewAI agent definitions
    ├── action/            ← Perplexity Comet flows that file the ticket
    └── cli.py             ← `bellwether run --supplier <id>`
```

Secrets and research are kept **outside** this folder on purpose:

- [`../keys/`](../keys/) — `.env` and the signup checklist (gitignored)
- [`../research/`](../research/) — ideation HTMLs, sponsor mapping, build plan

This means the submission can be zipped or pushed by archiving the
`Bellwether/` folder alone — no token leaks, no working-doc noise.

---

## Run it

```bash
# from the repo root
cd Bellwether
pip install -e .                  # registers the `bellwether` package
python config.py                  # confirms all tokens are set
bellwether run --supplier acme    # one supplier, end-to-end
bellwether run --all              # the morning batch
```

The build is staged across five days; see the build plan for what ships when.
