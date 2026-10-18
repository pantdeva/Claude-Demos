# Session Context — 16 Oct 2026 (IST)

Summary of a working session with Claude covering GitHub setup, an STA (Static Timing Analysis) learning kit, and an NLP-based stock analyzer. Secrets (such as the NewsAPI key) are deliberately left out.

---

## 1. GitHub setup

- **Repository:** `pantdeva/Claude-Demos` (GitHub now lists it with this capitalisation; the old `claude-demos` URL still works).
- GitHub was linked through Claude's GitHub integration on claude.ai (there is no separate "GitHub connector").
- **Default-repo skills:** `default-git-repo` (pointed to `pantdeva/Claude-Devs`) was updated to "no default repo". `demos-default-repo` still points to `pantdeva/Claude-Demos`.
- **Initial structure on `main`** (commit `6c5fd86`): `src/Finance`, `src/ML`, `src/Electronics`, each with a `.gitkeep`.

### Branches

| Branch | Based on | Contents |
|---|---|---|
| `main` | — | Folder skeleton only |
| `STA` | `main` | `4654680` "First Stage STA repo bringup" — two STA decks |
| `ML` | `main` | Stock analyzer (see §3); latest commit `d0b668e` |

**Tag `V2.0.0`** ("Financial Prediction Tool Phase 1") could not be pushed from the session (the session's git proxy returned HTTP 403 for tag pushes). Create it on GitHub: Releases → Draft a new release → tag `V2.0.0`, target the latest `ML` commit.

---

## 2. STA learning kit (branch `STA`)

Location: `src/Electronics/STA KB/Ramp/`

### Background
- The original plan was to transcribe the YouTube "STA Series" by *Chip Design with Rashid* (playlist `PL0-xus8sJBCTw1aDsx3RXQv3D8MfYJ602`) into one deck per video. YouTube blocks automated transcript access, so that plan was dropped.
- Instead, a web-researched ramp-up plan was built covering (1) timing analysis available in each tool and (2) the kinds of modelling available, mapped to the playlist video titles the user supplied (Weeks 1, 2, 5, 6, 7, 8, 10, 11, 12). Videos are mapped by title only; their content was not transcribed.

### Deliverables
1. **`STA_Ramp_Up_3_Day_Plan.pptx`** (14 slides)
   - Day 1 — Foundations & inputs (playlist weeks 1–5)
   - Day 2 — Running STA (weeks 6–9)
   - Day 3 — Margins & full chip (weeks 10–12)
   - Per-day playlist-to-session mapping with readings
   - Constraints section: six kinds of constraints (clock definition, clock characteristics, I/O & environment, timing exceptions, design rules, modes & analysis control) and what each tells the tool
   - Tool capability table (PrimeTime, Tempus, Fusion Compiler/ICC II, Genus/Innovus, Aprisa, OpenSTA, Ansys Path FX) and modelling stack (NLDM→CCS/ECSM, wire-load→SPEF, flat OCV→AOCV→POCV/SOCV→LVF, noise, ETM/ILM/SmartScope, SDC/SDF)
2. **`Running_PrimeTime.pptx`** (11 slides): inputs/outputs, working-area layout and setup files (`.synopsys_pt.setup`, `common_setup.tcl`, `pt_setup.tcl`, `pt.tcl`), library variables, three ways to launch `pt_shell`, the six-step run flow, a minimal run script, sanity checks, reports, sessions.

### Core reading set (kept common across topics)
- Bhasker & Chadha, *Static Timing Analysis for Nanometer Designs* (Springer, 2009) — mapped by chapter
- Liberty User Guides and Reference Manual (2017.06)
- Your tool's documentation (PrimeTime/Tempus datasheets & user guide; OpenSTA README)

Caveat: PrimeTime commands come from public university labs (Lund, UT Austin) and lab notes, not Synopsys's SolvNet user guide; confirm syntax with `man <command>` in `pt_shell`.

---

## 3. NLP stock analyzer (branch `ML`)

Location: `src/Finance/nlp_stock_analyzer/` (moved from `src/ML` in its own commit).

### Design choices (made by the user)
- **News source:** NewsAPI (`/v2/everything`)
- **NLP engine:** FinBERT (`ProsusAI/finbert`)
- **Markets:** US and India
- **Output:** Streamlit dashboard (plus a CLI runner added later)

### Four factors
| Factor | Searches | Direction |
|---|---|---|
| Market sentiment | News naming the company | as scored |
| Competition & news releases | Company announcements (+) and competitor news | competitor news flipped (−1) by default |
| Manufacturing industry | Suppliers / inputs / production side | as scored |
| Customers | Key customers and end markets | as scored |

Scoring: FinBERT `P(positive) − P(negative)` per headline+description; recency-weighted (half-life 3 days) mean per factor; composite = weighted mean of factors with news; Bullish ≥ +0.15, Bearish ≤ −0.15.

### Files
- `app.py` — Streamlit dashboard
- `run.py` — CLI runner (`python run.py NVDA MU --days 7`; `--scorer numpy --model-dir ./finbert` to run without PyTorch)
- `config/companies.yaml` — tickers (NVDA, MU, TATASTEEL.NS), factor terms, context/exclude words, weights, thresholds, excluded sources
- `stock_analyzer/` — `config.py`, `factors.py`, `news.py` (NewsAPI client, hour-rounded cache), `sentiment.py` (FinBERT via transformers), `finbert_numpy.py` (same model in NumPy), `analyzer.py`
- `tests/test_analyzer.py` — 20 offline unit tests

### Relevance fixes after the first live run
- Capitalised terms are case-sensitive (`Intel` ≠ "intel sharing"; `SAIL` ≠ "sail")
- Per-company `context` words (e.g. Microsoft only counts with AI/capex/chips) and `exclude` words
- `exclude_sources` for deal sites (Slickdeals, Dealcatcher, …)
- Competitor stories that also name the company stay in market sentiment
- Syndicated headlines counted once per factor
- NewsAPI cache keys rounded to the hour so reruns don't spend quota

### Live results (7-day window ending 16 Oct 2026)

| | NVDA | Tata Steel | Micron (MU) |
|---|---|---|---|
| **Composite** | +0.14 Neutral | +0.26 Bullish | −0.06 Neutral |
| Market sentiment | +0.10 (73) | +0.06 (5) | −0.32 (80) |
| Competition & releases | +0.15 (125) | −0.20 (5) | +0.15 (82) |
| Manufacturing industry | +0.32 (75) | +0.45 (14) | +0.13 (85) |
| Customers | +0.05 (55) | +0.83 (4) | −0.09 (47) |

(article counts in brackets)

Notes:
- Tata Steel scores rest on few articles (thin Indian coverage in NewsAPI).
- FinBERT scores tone, not company impact (e.g. a coking-coal price hike reads positive but hurts a steelmaker).
- For MU, competitor news (Samsung, SK Hynix falling in a sector-wide sell-off) was flipped to positive, inflating the competition score. Suggested fix: a per-company option to treat competitor news as a sector signal (not yet implemented).

### Environment notes
- Session runs used FinBERT via the NumPy implementation because PyPI was blocked (no PyTorch/transformers/Streamlit). Output verified on reference headlines (e.g. "Stocks rallied and the British pound gained." → positive 0.90).
- Network allowlist on claude.ai (Settings → Capabilities) was extended to newsapi.org, huggingface.co and *.hf.co.
- NewsAPI free plan: 100 requests/day, articles up to one month old, 24-hour delay, development use only.
- The NewsAPI key was shared in chat — regenerate it at newsapi.org if desired. It is not stored in the repo.

### Run locally
```bash
cd src/Finance/nlp_stock_analyzer
pip install -r requirements.txt
export NEWSAPI_KEY=your_key
streamlit run app.py          # dashboard
python run.py NVDA MU --days 7  # CLI
```

---

## 4. Open items
1. Create tag `V2.0.0` on GitHub (Releases), targeting the latest `ML` commit.
2. Optional: add a per-company "competitor news as sector signal" setting (helps MU).
3. Optional: `demos-default-repo` skill still sets Claude-Demos as default — update or disable if no default is wanted.
4. Optional: merge `STA` and `ML` into `main` via pull requests.
