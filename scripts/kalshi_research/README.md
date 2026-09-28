# Kalshi Research Scripts

Standalone analysis scripts from the Kalshi edge search. They have **no dependency on
`src/`** and use only the Python standard library, so they run in a bare
`python:3.12-slim` container.

Results and interpretation live in `docs/KALSHI_EDGE_SEARCH_CLOSEOUT.md` and the documents it
links. API field semantics are in `docs/KALSHI_API_SCHEMA_REFERENCE.md` — read that before
modifying any of these, because five of its entries were guessed wrong first and each wrong
guess produced a confident false result.

## Running

These were developed on an EC2 host at `/var/lib/kalshi-research`, mounted at `/data`:

```bash
sudo tee /var/lib/kalshi-research/<script>.py >/dev/null < <script>.py
sudo docker run --rm -v /var/lib/kalshi-research:/data \
  python:3.12-slim python3 -u /data/<script>.py
```

Three operational notes that cost real time to learn:

- That directory is **root-owned**, so a plain `cat > file` redirect fails silently while a
  subsequent `docker run` proceeds against a nonexistent file. Use `sudo tee`.
- Scripts that write output need the mount **writable** — not `:ro`.
- Validate with `python3 -m py_compile` before a long run. A line count is not proof the
  paste survived.

## Scripts

| script | purpose | runtime |
|---|---|---|
| `wxmmf.py` | Fetch weather MM dataset: candles + full trade tapes for 8 series → `/data/wxmm.json` | ~30 min |
| `wxholdout.py` | **FROZEN 2026-09-27.** Preregistered forward test evaluator. Do not edit. | seconds |
| `wxmms3.py` | Market-making grid, maker fee correctly at zero | seconds |
| `wxdiag.py` | The diagnostic that caught the weather settlement retraction | seconds |
| `corr.py` | Strike-ladder arbitrage screen across ~3,400 series | ~13 min |
| `mxarb.py` | Multi-outcome arbitrage over `mutually_exclusive` events | ~2 min |
| `fund.py` | Cross-venue perpetual funding logger, 5-minute polls (long-running) | continuous |

## The architecture that made these usable

**Fetch once, cache, analyse repeatedly.** Early runs in this project re-pulled the same
candlesticks for every question — three separate 20-35 minute runs that all shared one bug and
could not have detected it. `wxmmf.py` writes a JSON cache; `wxmms3.py`, `wxholdout.py` and
`wxdiag.py` all read it and finish in seconds. That is what made it cheap to re-run an analysis
after finding a fee error, rather than expensive enough to avoid.

## Two invariants these scripts encode

**Quote from the previous bar, never the current one.** `wxmmf.py` and `wxmms3.py` rest quotes
at the *previous* hour's closing bid/ask. Using the same bar's close lets information from
after the trade set the price we quoted — the one-bar lookahead that faked a z=+41 signal
earlier in this project.

**Sort trades ascending before selecting an entry.** `/markets/trades` returns
**newest-first**. Taking `trades[0]` as "the first trade" produces +5.88c where the honest
answer is -3.01c. `wxmmf.py` stores `created_time` and sorts.

## Not archived here

These remain only on the EC2 host and can be re-added if needed: `wxfetch.py`, `wxpnl.py`
(the retracted weather implied-mean arc), `wx2fetch.py`, `wx2cal.py`, `wx2pnl.py` (multi-horizon
calibration, PIT and executable P&L), `fwdsum.py`, and the `dbg*.py` schema probes whose
findings are all captured in `docs/KALSHI_API_SCHEMA_REFERENCE.md`.

Cached datasets (`wxmm.json` ~89MB, `corr_snap.json`, `mx_snap.json`) are deliberately not in
Git. All are regenerable from the fetch scripts.
