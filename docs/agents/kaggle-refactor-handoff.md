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

The plan is committed at `4bee87c7d`, the builder at `b57f61b09` and the
bootstrap notebook at `3e8327590`. Nothing has been executed on Kaggle yet, and
the builder's test suite has not been executed at all — see
[Local verification](#local-verification) before trusting either.

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
| Session lifecycle from the app (2026-11-16, owner) | **Shutdown only** — an authenticated notebook route (`POST /api/session-control/shutdown`) plus a Settings → Sharing → Remote backend button end the kernel and release the GPU; *starting* stays a human *Run* on Kaggle, so the app still never holds Kaggle API credentials |

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
| T6 | 2026-11-16 | Dataset builder: hub-cache layout from `revision_for`, `manifest.json` (SHAs, sizes, per-file sha256), `--verify`, `--zip`, `dataset-metadata.json`; test reads the result back through `model_catalogue` and `hf_revisions` | `b57f61b09` | `scripts/build_kaggle_dataset.py`, `tests/scripts/test_build_kaggle_dataset.py` | done, **pytest not run** (see [Local verification](#local-verification)) |
| T7 | next | Read-only cache support (gap 1) — argued as unnecessary under `HF_HUB_OFFLINE=1`, unproven on a live mount | — | — | not started |
| T8 | 2026-11-16 | Licence pre-acceptance for ephemeral sessions (gap 2): `scripts/kaggle_preaccept_licenses.py` records the Max pack through `model_acceptance.accept()` bound to the live terms fingerprint, refuses to run without `OMNIVOICE_DATA_DIR`; explicit notebook cell runs it before uvicorn starts | `526e95fb2` | `scripts/kaggle_preaccept_licenses.py`, `tests/scripts/test_kaggle_preaccept_licenses.py`, notebook licence cell | code done, stdlib-level tests pass locally, **not exercised on Kaggle** |
| T9 | 2026-11-16 | Bootstrap notebook: dataset discovery, Docker-equivalent install, cuDNN 8 side-load, uvicorn in server mode against the read-only cache, `/health` wait, `/models` pack check, Cloudflare quick tunnel, printed URL + key | `3e8327590` | `notebooks/VoiceStudio_Kaggle_2xT4.ipynb` | code done, **never run on Kaggle** |
| T10 | next | HF token in the setup wizard | — | — | not started |
| T11 | last | Multi-GPU placement (gap 5) | — | — | not started |
| T12 | 2026-11-16 | Session shutdown control: notebook `session_control.py` sidecar (Bearer-gated route, tunnel pidfile → kernel SIGTERM/SIGKILL → `os._exit`), `shutdownRemoteSession` in Electron main + IPC + Settings button with confirm, 7 strings × 22 locales, notebook contract test | `e727d259f` | `notebooks/VoiceStudio_Kaggle_2xT4.ipynb`, `electron/src/main/remote-backend.ts`, `electron/src/renderer/src/features/settings/remote-backend-settings.tsx`, `tests/test_kaggle_session_control.py` | code done, **not run on Kaggle; Electron tests not run locally** (no bun/node_modules on the dev machine) |

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
| A keyed request is never `Host`-checked | `backend/core/browser_guard.py` → `_network_authorized_only`, `is_cross_site` | read both |
| The notebook installs like Docker, not like a venv | `notebooks/VoiceStudio_Kaggle_2xT4.ipynb` (install cell); `deploy/torch-constraints.txt` header; `notebooks/OmniVoice_Studio_Colab.ipynb` cell 2e | read the three |
| cuDNN 8 side-load is found beside `<repo>/.venv` | `backend/core/cudnn8.py` → `compat_dirs`; `scripts/setup.py` → `_find_compat_dir` | read both |

## Local verification

T6's tests were written but **never executed**: this machine has no `.venv`, no
`uv` and no `pytest`, and its system Python 3.15 has no `huggingface_hub` or
`PyYAML`, so `model_catalogue.catalogue_entry()` degrades to an empty catalogue.
The builder itself was exercised by a throwaway script against a synthetic
snapshot (layout, `refs/main`, marker, hash + digest, tamper detection, zip
paths, overwrite refusal, and `_snapshot_dirs` / `installed_revision` agreeing),
which caught two real defects that are fixed in `b57f61b09`: a `Path`-vs-`ZipFile`
mistake in a test, and a tamper case whose replacement byte-length also tripped
the size check.

Before trusting T6, run:

```sh
uv run pytest tests/scripts/test_build_kaggle_dataset.py -q
```

(The file failed to even collect until `6044f642b` — pytest imports it as
`scripts.test_*` because `tests/scripts/` has an `__init__.py`, which shadowed
`from scripts import build_kaggle_dataset`. It now loads the script by path.)

## Where the agent stopped

End of **T8 code**: the plan (`4bee87c7d`), the builder (`b57f61b09`), the
notebook (`3e8327590`), the session-shutdown control (`e727d259f`: notebook
sidecar route + Electron `shutdownRemote` IPC + Settings → Sharing button +
locale strings + `tests/test_kaggle_session_control.py`) and the licence
pre-acceptance (`526e95fb2`) are committed; the README was rebranded for the
fork just before (`17efe667e`, see `git log`). A latent collection error in
T6's test file was fixed on the way (`6044f642b`: `tests/scripts/__init__.py`
shadowed `from scripts import …`). **Nothing has run on Kaggle**; the
builder's tests still need the full uv env and the Electron-side T12 tests
need bun (neither exists on this machine — the stdlib-level suites did pass).
T7/T10/T11 are untouched.

## Where the next agent starts

1. **T9 verification — the first real GPU session.** Attach the built dataset,
   run the notebook on 2 × T4, and record in this page: install wall time,
   `/health` time, cold first-generate time, `nvidia-smi` memory per engine, and
   whether the read-only mount throws any write. That run is what converts T9
   from code to evidence, and it decides whether T7 is real work or a no-op.
   In the same session, exercise T12 end to end: connect the desktop app,
   press **Shut down session**, and verify the 202, the tunnel dying, the
   kernel exiting, and Kaggle marking the session ended (quota stops).
2. **T7 — read-only cache, if the session shows a write.** Teach the
   download/repair path to tolerate a cache it cannot write: no `refs/` write
   required, no lock file required, a clear error when a snapshot needs repair.
   Test: a chmod-0555 cache root serves a model without a write attempt.
3. ~~**T8 — licence pre-acceptance.**~~ **Done** (`526e95fb2`): the notebook's
   licence cell runs `scripts/kaggle_preaccept_licenses.py` through the real
   fingerprinted gate. Verify it live during T9: a fresh session must not ask
   again for NLLB-200 or the OmniVoice weights.
4. **T10 — HF token in the wizard.** Mount `HuggingFaceToken` in step 1 of
   `setup-wizard.tsx`; no new strings. Test: a gated repo shows the token field
   before the download starts.
5. **T11 — multi-GPU.** Placement across two devices: device list in
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
