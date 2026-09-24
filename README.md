# Helpdesk — Daily Operations Dashboard

A daily operational monitoring tool for a customer-support helpdesk. It turns a raw ticket
extract into a view of how much work is arriving, how much is being cleared, how quickly,
and where the workload sits.

The intended user is a **Helpdesk Team Lead**, whose job with it is to monitor the health of
the queue and spot where intervention is needed. It is built to be read in order — headline
numbers first, then the trends behind them, then the breakdowns — rather than browsed.

The design it implements (purpose, users, metrics, filters and layout) is specified here:
[Dashboard design](https://ignaciomarininbox.atlassian.net/wiki/spaces/PRPS/pages/126091265/Take+Home+Assignment).

## The questions it answers

| Question | Where |
|---|---|
| How much work is coming in? | Created tile, demand-vs-last-week chart |
| How much is being completed? | Resolved tile, created-vs-resolved trend |
| Is work accumulating? | Backlog tile and trend, net change, resolved-to-created ratio |
| How quickly are tickets resolved? | Median and P90 turnaround, turnaround trend |
| Does any language or ticket type behave differently? | Segment panels, drill-down tab |
| When does the work actually arrive? | Hour × weekday heatmap, weekday volume |
| Can the numbers be trusted? | Data & quality tab, metric dictionary |

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-streamlit.txt   # dashboard + aggregation
.venv/bin/pip install -r requirements-notebook.txt    # the two notebooks

.venv/bin/streamlit run dashboard.py                  # http://localhost:8501
```

The dashboard builds whatever it needs on first launch. To rebuild from the raw file, run
the notebooks in order — see below.

## Workflow

```
data/raw/*.xlsx
      │
      ├── data_source_review.ipynb ──► data/clean/data_quality_issues.csv
      │                                 (findings, shown on the dashboard)
      │
      └── data_cleaning.ipynb ────────► data/clean/tickets_clean.csv
                                              │      THE maintained file
                                              │
                                   pipeline/build.py
                                              │
                                        data/clean/derived/
                                        kpi_*.csv, headline_kpis.json
                                              │
                                         dashboard.py
```

**`data/clean/tickets_clean.csv` is the only file that has to be maintained.** Everything
under `derived/` is recomputed from it and can be deleted at any time.

Two mechanisms keep that true:

- the cleaning notebook runs `pipeline/build.py` as its final step, so the aggregates are
  refreshed in the same pass that produces the clean file;
- the dashboard's loader compares modification times and rebuilds the aggregates if they
  are older than the clean file, whatever produced it.

So re-running the cleaning notebook refreshes everything downstream, and the dashboard
cannot serve aggregates older than their source.

## Project structure

```
data/raw/                      the source workbook, never modified
data/clean/tickets_clean.csv   analysis-ready tickets — the maintained source
data/clean/data_quality_issues.csv   the review's findings, read by the dashboard
data/clean/derived/            aggregates, fully recomputable

data_source_review.ipynb       is the source data fit for this dashboard?
data_cleaning.ipynb            raw workbook -> tickets_clean.csv

pipeline/build.py              aggregates the clean file into derived/
pipeline/verify.py             85 checks, re-derived from the raw workbook

dashboard.py                   the Streamlit app (four tabs)
app/data.py                    loading, rebuild-if-stale, cache invalidation
app/metrics.py                 metric definitions shared by pipeline and dashboard
app/charts.py                  chart builders, one per analytical job
app/theme.py                   colour tokens and shared plotly layout
app/branding.py                CSS, header, KPI tile markup

tools/audit_metrics.py         independent recomputation of every dashboard metric
tools/audit_vs_dashboard.py    asserts the dashboard matches that recomputation
tools/demo_synthetic_tat.py    reproduces the generated-timestamp evidence
tools/validate_palette.py      colour-accessibility validator for app/theme.py
```

## The notebooks

### `data_source_review.ipynb` — is the data fit for purpose?

Profiles the two source tables before anything is built on them: missing values,
duplicates, key integrity, the language join, date formats and precision, the shape of the
turnaround distribution, categorical domains, and the consistency of fields that describe
the same thing.

It ends with a prioritised list of **16 data-quality issues**, seven of which affect core
metrics, written to `data/clean/data_quality_issues.csv` and displayed on the dashboard's
*Data & quality* tab — so the findings are maintained in one place rather than retyped.

Each finding is derived on screen rather than asserted: the checks print their evidence.

### `data_cleaning.ipynb` — raw workbook to analysis-ready table

Applies the decisions the review reached. No rows are added or removed — everything is
renamed, derived or dropped.

| Step | What it does |
|---|---|
| Rename and drop | Readable field names; removes columns that carry no information |
| Timestamps | Explicit parsing rather than relying on how Excel is read |
| Split ticket type | `Ticket Type` holds queue *and* refund category; splits into `queue` + `request_type` |
| Date parts | Day, hour and weekday for grouping (UTC) |
| Turnaround | Derived, and named so its status is unmissable |
| Refund flags | Nullable booleans, so missing values survive the round trip |
| Ticket attributes | Weekend flag, same-day flag, repeat-contact sequence and gap |
| Sort and order | Chronological, stable column order |
| Checks | Row count, key uniqueness and permitted nulls, before saving |
| Rebuild | Runs `pipeline/build.py` so the derived layer never lags |

## The dashboard

Four tabs, each with a distinct job.

**01 · Operations Overview** — the one-screen view. Five tiles (created, resolved, backlog,
median TAT, P90 TAT), then demand against the same weekday a week earlier, created vs
resolved, whether work is accumulating, backlog and turnaround trends, backlog by age, and
per-segment breakdowns by language queue and request type.

**02 · Drill Down** — what is driving the numbers: mix by ticket type and queue over time,
when work arrives by hour and weekday, repeat-contact gaps, the turnaround distribution,
and ticket-level export.

**03 · Data & quality** — the issue list from the review, filterable and downloadable, the
recommended KPI set with a confidence column, and a timestamp showing when the clean
dataset was last refreshed.

**04 · Metric dictionary** — every metric's definition, why it matters and exactly how this
build computes it; plus the filters and the column each is built from.

Filters — date, language queue and request type — drive every figure on tabs 01 and 02.
Tab 03 describes the dataset as a whole and does not respond to them. Granularity is daily
only: the current extract spans 13 days, so a weekly view would be two partial weeks.

## Metrics

| Metric | Definition |
|---|---|
| Tickets Created | Tickets whose creation date falls in the period |
| Tickets Resolved | Tickets resolved in the period, among those created in it |
| Backlog / Open | Tickets created but not resolved, counted at 23:59 each day |
| Net Ticket Change | Created − resolved: is the pile growing, in absolute terms |
| Resolved-to-Created Ratio | Scale-free pace — comparable across segments of any size |
| Median TAT | Typical resolution time, robust to outliers |
| P90 TAT | The slow tail |

Backlog is counted by timestamp over every ticket, not as a running total of the daily
columns, so it stays correct for tickets that arrived before the selected range or never
resolve at all. P90 uses nearest-rank interpolation, because turnaround is whole minutes
and a linear percentile would report a value that cannot occur.

**Known divergence.** *Tickets Resolved* is currently a cohort measure — tickets created
inside the selected range and resolved inside it. The design specifies a throughput
measure: every ticket whose resolution date falls in the range, whenever it arrived. The
difference shows on the first day of a filtered range, which under-counts resolutions of
tickets that arrived the night before (14 tickets on 1 Jul for a 1–5 Jul range). Full-window
totals are unaffected. Backlog was moved to the throughput-style definition already;
Tickets Resolved has not been.

## What the data review found

Two findings shape how the dashboard is built:

**Turnaround is generated, not measured.** Every resolution timestamp is the creation
timestamp plus a whole number of minutes between 15 and 45, carrying the identical
millisecond — which only happens if it was calculated. The turnaround metrics are still
built exactly as they would be on real data, but they carry a `DATA ISSUES` badge, and the
column is named `turnaround_minutes_generated` so the status survives into any export.
Backlog inherits the ceiling: nothing can age beyond 45 minutes.

**The language field defaults to English.** `language_dwid` contradicts the queue on 17.5%
of tickets, always toward English, and degrades partway through the window. Language
reporting is built from the queue parsed out of `Ticket Type`; `language_dwid` is dropped
during cleaning.

The full list, with severity and handling, is on the *Data & quality* tab.

## Verification

```bash
.venv/bin/python pipeline/build.py     # rebuilds the aggregates, asserting as it goes
.venv/bin/python pipeline/verify.py    # must print "85 passed, 0 failed"
```

`build.py` asserts its own invariants — row counts reconcile, shares sum to 100%, P90 is
never below the median, backlog is non-negative and matches the midnight carry.

`verify.py` is the independent check: it re-reads the **raw workbook** and re-derives every
published figure through different code paths, then asserts the two agree. Where the
pipeline uses `Series.quantile`, it uses `numpy.percentile`; where the pipeline shifts a
series by seven days to find last week's figure, it looks each date up in a freshly
counted index. A number only one implementation produces is a number nobody has checked.

### Auditing the dashboard's numbers

`verify.py` checks the published tables. It does not check what the dashboard *shows* for a
given filter selection — that is what these two do:

```bash
python tools/audit_metrics.py --from 2022-07-01 --to 2022-07-05 --queue EN
python tools/audit_vs_dashboard.py     # must print "all 9 selections agree"
```

`audit_metrics.py` recomputes every figure the dashboard reports — tiles, daily series,
backlog by age, per-segment breakdowns — straight from the raw workbook, for any date range
and filter combination. It imports nothing from `app/` or `pipeline/` and never reads the
clean file: queue parsing, turnaround, backlog and percentiles are all re-implemented. Run
it alongside the dashboard and compare at a glance, or pass `--json` to diff.

`audit_vs_dashboard.py` automates that comparison. It drives the app headlessly across nine
filter selections, scrapes the numbers actually rendered, and asserts they match the audit —
the five tiles, the accumulation caption and every row of the daily table. It exits non-zero
on disagreement, so it works as a pre-commit or CI gate. This is the check that catches a
filter silently not being applied, or a metric quietly changing definition.

It earned its place on the first run by catching a real defect: a day with no tickets in the
current selection dropped out of the daily frame entirely, so the trend lines joined the days
either side as if they were adjacent. Visible only when filtering to a small segment.

### Dashboard smoke tests

The dashboard is also tested headlessly across filter paths that have broken before — empty
selections, single-language queues, one- and two-day windows:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("dashboard.py", default_timeout=300); at.run()
assert not at.exception
```

## Notes

- **Times are UTC.** Every daily figure is a UTC day and will not match a local working day
  in every region.
- **Restart after editing `app/`.** Streamlit re-executes `dashboard.py` on rerun but keeps
  imported modules in `sys.modules`, so changes to `app/*.py` need a server restart.
- **No `requirements.txt`.** Dependencies are split by purpose. Streamlit Community Cloud
  auto-detects only that filename, so a deployment needs one containing
  `-r requirements-streamlit.txt`.
- **Colours are validated, not chosen by eye.** The categorical palette in `app/theme.py`
  clears OKLab Delta E, dichromat simulation and WCAG contrast gates;
  `tools/validate_palette.py` reproduces the result.
