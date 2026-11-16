# Kaggle remote-GPU refactor — timeline and handoff

This page is the handoff record for moving the Max model pack to a Kaggle
dataset and using the free 2 × T4 session as a remote backend. Read it before
touching anything: it says what was decided, what was only investigated, and
where the next agent starts.

The feature guide is [docs/install/kaggle.md](../install/kaggle.md). That page
describes the target behaviour; this one records the state of the work.

## Truth rules

1. **The commit ledger is the only proof of progress.** A step is done when its
   row carries a SHA that `git show <sha> --stat` confirms.
2. A row whose commit column is `—` was recorded before the repository existed.
   Those rows are claims backed by the files named in
   [Evidence map](#evidence-map); re-check them before building on them.
3. Append rows. Never rewrite a finished row to make the story cleaner.
4. Every new step ends in a commit. No commit, no completion.
5. Commits that only update this page are bookkeeping, not steps:
   `git log -- docs/agents/kaggle-refactor-handoff.md` lists them.

## Current status

Planning is complete, the owner has fixed the scope, and the plan is committed at
`4bee87c7d`, the baseline commit of this branch. **No product code has been
written for this refactor.**

## Remaining setup

| Item | State | Action |
| --- | --- | --- |
| Repository | `main` tracks `origin` (`orivaldogama/SmartStudio`); `4bee87c7d` is the baseline | — |
| Identity | `ORIVALDO DE HOLANDA GAMA <53544978+orivaldogama@users.noreply.github.com>`, set with `git config --local` | — |
| Push | One command, never a rewrite | `git push origin main` after each commit — a fast-forward while the fork's `main` has no newer commits |
| Changelog fragment | Missing | Needs the PR number: `changelog.d/<PR#>.<type>.md` |

The history starts at the fork's own `main`, not at an empty root, so pushes stay
fast-forwards and merging upstream keeps working. Do not run `git init` again.

## Decision log — 2026-11-16 (owner)

| # | Question | Decision | Consequence |
| --- | --- | --- | --- |
| 1 | How the app consumes the session | **Desktop, via Settings → Sharing → Remote backend** | No need to ship the built SPA to Kaggle; gap 3 is optional |
| 2 | Audience | **Personal, non-commercial use only** | Fits Kaggle's Terms of Use; dataset stays private |
| 3 | What survives the session | **Nothing — ephemeral** | No *Save Version* automation, no sync job, no 20 GB budget work |
| 4 | Dataset contents | **Max pack only, ~8.5 GB** | No alignment/demucs weights, no runtime wheels |
| 5 | Second T4 | **Multi-GPU refactor** | Largest single work item; schedule it last |
| 6 | Repository scope | **Official scripts + notebook + docs** | Builder, notebook, runbook, manifest test all land in-tree |

Two follow-up answers given in the same session:

| Topic | Decision |
| --- | --- |
| Hugging Face token in the setup wizard | **Yes** — mount the existing `HuggingFaceToken` component; small, reuses shipped strings |
| Kaggle API key in the wizard | **No** — the app never talks to Kaggle; a full-scope account key in the product is the wrong boundary |
| LLM "brain" (Llama) | Out of the Max pack; if wanted, a separate opt-in pack, 3B–8B Q4 on the second T4 |

## Timeline

T0–T4 predate the repository and were committed together at T5; their commit
column names that commit instead of pretending each had its own.

| # | Date | Step | Commit | Evidence | State |
| --- | --- | --- | --- | --- | --- |
| T0 | 2026-11-16 | Surveyed the Max pack, HF cache detection, headless/server mode, remote-backend path, GPU dispatch | `4bee87c7d` | see [Evidence map](#evidence-map) | done |
| T1 | 2026-11-16 | Verified Kaggle limits and Terms from upstream sources (T4 ×2, 12 h, 30 h/week, 20 GB, no inbound ports) | `4bee87c7d` | [docs/install/kaggle.md](../install/kaggle.md) | done |
| T2 | 2026-11-16 | Corrected the `AGENTS.md` row for `frontend/`. The rest of that file was already restructured in the working copy before this session; the commit carries both and its message says so | `4bee87c7d` | `git show 4bee87c7d -- AGENTS.md` | done |
| T3 | 2026-11-16 | Owner decisions recorded (six questions, three follow-ups) | `4bee87c7d` | decision log above | done |
| T4 | 2026-11-16 | Wrote the feature guide and this handoff page | `4bee87c7d` | `git show --stat 4bee87c7d` | done |
| T5 | 2026-11-16 | Established the repository on the fork's `main` and committed the plan and this page | `4bee87c7d`, `d59d74f9d` | `git show --stat 4bee87c7d` | done |
| T6 | next | Dataset builder + manifest + test | — | — | not started |
| T7 | next | Read-only cache support (gap 1) | — | — | not started |
| T8 | next | Licence pre-acceptance for ephemeral sessions (gap 2) | — | — | not started |
| T9 | next | Bootstrap notebook + runbook verification on a real session (gap 5) | — | — | not started |
| T10 | next | HF token in the setup wizard | — | — | not started |
| T11 | last | Multi-GPU placement (gap 7) | — | — | not started |

## Evidence map

Each claim below was checked against the file named, at the symbol named — use
the symbol, not a line number, because lines rot.

| Claim | Proof | Re-check |
| --- | --- | --- |
| Max pack is five repositories | `electron/src/renderer/src/features/settings/performance-model-packs.ts` → `performancePackRepos.max` | read the constant |
| Sizes and roles of those repos | `backend/config/models.yaml` → entries with `repo_id` for the five repos | read the entries |
| "Installed" means a snapshot directory with weights | `backend/services/model_catalogue.py` → `_hub_cache_roots`, `_snapshot_dirs`, `snapshot_is_complete` | read the functions |
| Runtime downloads are pinned to reviewed SHAs | `backend/services/hf_revisions.py` → `revision_for`; pins in `backend/config/model_licenses.json` | read the module |
| The backend can serve the web UI at `/` | `backend/main.py` SPA mount; `backend/core/spa_inject.py` → `frontend_dist_dir` (`OMNIVOICE_FRONTEND_DIST`) | read the mount block |
| Server mode + bind host + API key | `backend/main.py`, `deploy/Dockerfile` (`OMNIVOICE_SERVER_MODE`, `OMNIVOICE_BIND_HOST`), `backend/api/dependencies.py` (key gate) | read the env reads |
| Desktop can point at a remote backend | `electron/src/renderer/src/i18n/locales/en.json` → `settings.remote_backend_*`; Settings → Sharing section | search the keys |
| Licence acceptance survives pre-installed weights | `backend/services/model_acceptance.py` → `ensure_engine_accepted`; called from `backend/services/model_manager.py` `get_model` | read both |
| One GPU per process | `backend/core/device_caps.py` note "`N` GPUs detected; routing reflects device 0"; `backend/services/model_manager.py` → `_pick_gpu_workers`, `get_best_device` | read both |
| The GPU pool is sized from device 0's free VRAM | `backend/services/model_manager.py` → `_workers_for_free_vram`, `_pick_gpu_workers` | read both |
| Data root and cache are redirectable | `backend/core/config.py` → `get_app_data_dir` (`OMNIVOICE_DATA_DIR`), Windows cache redirection | read the module |
| WhisperX alignment defaults to CPU | `backend/services/asr_backend.py` → `forced_align` (`OMNIVOICE_ALIGN_DEVICE`) | read the function |
| HF token UI already exists | `electron/src/renderer/src/features/settings/credential-settings.tsx` → `HuggingFaceToken` | read the component |
| Wizard layout (4 steps, model packs at step 1) | `electron/src/renderer/src/components/setup-wizard.tsx` → `steps` | read the constant |

## Where the agent stopped

End of **T5**: the plan is committed at `4bee87c7d`, nothing is pushed, and no
refactor code has started. The next step is T6.

## Where the next agent starts

Each step is its own commit; do them in this order.

1. **T6 — dataset builder.** A script under `scripts/` that materialises the HF
   cache layout from `revision_for(repo_id)`, writes `manifest.json`
   (`repo_id`, `revision`, `size_bytes`, file count) and prints the eight sizes
   against the 200 GB cap. Test: a fixture cache tree is recognised as installed
   by `model_catalogue` without touching the network (`HF_HUB_OFFLINE=1`).
   *Done when* the test fails before the change and passes after.
2. **T7 — read-only cache.** Teach the download/repair path to tolerate a cache
   it cannot write: no `refs/` write required, no lock file required, a clear
   error when a snapshot needs repair. Test: a chmod-0555 cache root serves a
   model without a write attempt.
3. **T8 — licence pre-acceptance.** A documented, explicit bootstrap input that
   records acceptance for the named models in the ephemeral data root. Not a
   bypass of `model_acceptance`; the same fingerprint check must still apply.
4. **T9 — notebook + runbook.** `notebooks/` bootstrap that installs deps, sets
   the environment from [docs/install/kaggle.md](../install/kaggle.md), starts
   the tunnel and prints the URL. Verify end to end in a real 2 × T4 session and
   record the measured timings in this page.
5. **T10 — HF token in the wizard.** Mount `HuggingFaceToken` in step 1 of
   `setup-wizard.tsx`; no new strings. Test: a gated repo shows the token field
   before the download starts.
6. **T11 — multi-GPU.** Placement across two devices: device list in
   `HostCaps`, `get_best_device()` returning an indexed device, per-device GPU
   pool and admission, engine pinning (TTS on 0, ASR/translation on 1). Must be
   opt-in and fall back to today's single-device behaviour, so macOS and
   single-GPU hosts keep identical defaults.

## Picking this up on another machine

1. `git clone https://github.com/orivaldogama/SmartStudio.git` — or copy this
   folder including `.git`.
2. `git log --oneline -3`: `4bee87c7d` is the baseline commit of this refactor;
   anything newer is the most recent step.
3. Read **Where the agent stopped** and **Where the next agent starts** above.
4. Re-run the checks in **Evidence map** before trusting a row — files move.

`origin` is `orivaldogama/SmartStudio` (public fork of `debpalash/VoiceStudio`,
default branch `main`). Fetch upstream before branching for a PR, per the merge
protocol in `AGENTS.md`.

## Verification commands

Run these before claiming a row is true:

```sh
# the five Max-pack repos
grep -n "max:" electron/src/renderer/src/features/settings/performance-model-packs.ts

# cache detection contract
grep -n "snapshots" backend/services/model_catalogue.py

# pinned revisions
grep -n "def revision_for" backend/services/hf_revisions.py

# the two knobs that make a remote server reachable
grep -rn "OMNIVOICE_BIND_HOST\|OMNIVOICE_SERVER_MODE" backend/main.py deploy/Dockerfile

# single-device assumption
grep -n "routing reflects device 0" backend/core/device_caps.py
```

Docs pages must keep their relative links valid:
`uv run pytest -q tests/test_docs_links.py`.

## Still open

- Where the dataset lives: the owner's own Kaggle account, or a dedicated one.
- Whether the 29 GB RAM and 4 vCPU are enough for dubbing in a real session —
  measure at T9, do not assume.
- Whether multi-GPU is worth its risk before T9 proves the single-GPU path is
  usable end to end.
