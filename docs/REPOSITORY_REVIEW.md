# Repository review and release readiness

Baseline: Garmin Tracking v0.25.0 on main plus the unmerged interpretation work.
The ordered plan lives in [ROADMAP.md](../ROADMAP.md#repository-and-coaching-review).

| Workstream | Coverage | Decision and evidence |
|---|---|---|
| Inventory | Every one of the 152 tracked baseline files read. 116 text files, 21,953 lines, including 72 Python files. The 36 PNGs were checked for duplicate bytes. | AST parsed production and test code, identified functions with no static private references, compared exact function bodies with at least four statements, and resolved all eight CLI targets and 55 MCP decorators. Exact duplicate hashes and exact nontrivial function bodies were absent. |
| Dynamic entry points | Inspected Mac login, console commands, source adapters, sync, disabled publishing and weather guards, detached narration and dashboard rebuild. | Some entry points have no direct import caller. Login is a documented module command. Source adapters are imported in the sync factories. Weather and protected publishing are opt-in paths with existing tests. Keep them. |
| Cleanup | Confirmed the unused trial timestamp helper and running/bedtime arguments against repository callers. | Remove those dead paths. Keep the redirect override, source interface and importer divider flagged by the exploratory lint pass. Consolidate agent rules under AGENTS.md and point CLAUDE.md there. Correct the MCP count in the architecture. |
| Interpretation UX | Chromium checked Today at 390 px and 1200 px. | The interpretation comes before the weekly card. The disclosure shows earlier evidence as text and links current readings to their corresponding pages. Both widths rendered without page-level overflow. |
| Config and continuity | Check time-budget compatibility, local persona loading, cache key inputs and prior evidence bounds. | Allow 1–30 minutes for the draft with a separate overhead budget. Keep a local profile outside Git and a small SQLite evidence memory. The model gets evidence only, with no private reasoning or earlier drafts. |
| Three-year replay | 36 sampled months on a generated archive. | Zero bad fragment links or duplicate IDs and a byte-identical source after replay. The source is synthetic. The owner's Mac archive was absent from the execution workspace. |
| Remaining manual audit | Complete review of every formula, old note, screenshot and every dynamic deployment branch is still open. | Continue by module ownership and use evidence before removing or consolidating code. Cover real archive replay, launchd, iCloud, and physical-device behavior separately. |

The static pass traversed all Python ASTs and checked each tracked file. It flags candidates for
inspection. Static references do not prove runtime use or correctness. Photos, screenshots,
research notes, and old changelog material are historical evidence even when current code does
not reference them. Keep those unless the owner chooses to retire them.
The documentation pass also resolved 141 repository-relative Markdown paths without a missing
file target.

## How to validate on the Mac

Use the existing local database and run `garmin-mcp-verify --replay-dashboard`. It opens the
source read-only, uses a temporary SQLite copy, renders up to 36 monthly snapshots, and prints
aggregate coverage and link counts. It sends no data to Ollama or a network service and does not
save rendered pages. The temporary disk needs space for a copy of the database.

## Model choice

- Qwen3.8 has a 27B local tag around 18 GB for the model alone. It is a candidate for drafting
  on a Mac with memory headroom. The current 8 GiB execution limit rules out loading that file
  here. [Qwen3.8 source](https://github.com/QwenLM/Qwen3.8) · [Ollama tags](https://ollama.com/library/qwen3.8/tags).
- Nimble v3 is a Qwen3.5-derived 9B decision fine-tune for classification, routing, and scoring.
  The tested 5.6 GB Q4 tag reported only the `decision` capability. Ollama rejected a live
  `/api/generate` request. Keep Qwen as the writer candidate. Nimble could be evaluated as a
  separate review classifier using its decision interface.
  [Publisher overview](https://ollama.com/library/nimble-v3) · [Local tags](https://ollama.com/library/nimble-v3/tags).
- On the fictional mixed recovery case, Qwen3.5 4B completed a direct run in about 55 seconds
  and the pipeline withheld the observation. Keep this case as a release check.
- On the fictional matched-run case, the same model hit the configured five-minute thinking
  limit. The direct retry was withheld. Total time was about 336 seconds on Linux CPU.
  A separate direct diagnostic showed two concrete problems: the draft inferred perceived
  effort from pulse data and introduced a sleep threshold without citing a sleep reading.
  The writer prompt now asks about repeat measurements without invented targets or perceptions.
  A direct retest of that case completed in about 55 seconds and was also withheld.
- Compare models on the same fictional cases. Record whether the model returned a useful
  reviewed observation, its latency, and whether it used thinking or a direct draft. Model
  file size and vendor benchmarks do not establish those outcomes for this workflow.
