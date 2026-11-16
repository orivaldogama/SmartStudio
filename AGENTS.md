## Active desktop: Electron only

Electron (`electron/`) is the only desktop and web UI. The Tauri shell and legacy
UI entrypoints are removed; do not restore build, runtime, release, or CI paths for
them. Triage reports from final Tauri installations toward the migration guide and
preserve their immutable updater feeds. Some modules under `electron/src/shared/` remain
temporarily shared by Electron; they are not a runnable app. New UI, IPC, setup
instructions, tests, and browser assets belong in Electron; validate Electron on
macOS, Windows and Linux.

## Mobile: native iOS and Android (owner-set 2026-10-17)

Every release builds desktop, iOS, Android and Docker from the same release tag
and version (owner-set 2026-10-26). Phone downloads belong on the same GitHub
Release; a missing channel is a release bug.

`mobile/ios/` (Swift/SwiftUI) and `mobile/android/` (Kotlin/Compose) are native
apps that run models **on the phone** (TTS, dictation, voice cloning, dub
translation; owner-set 2026-10-18) and can also drive a user's own VoiceStudio
computer. Phone first: once models are downloaded they work offline with no
computer; pairing adds the heavy engines, chosen per task. The companion-only
build is the base, not the product. They implement one shared contract,
`mobile/contract/SPEC.md`: a mobile feature ships on both or neither.
Theme, API and strings are generated, never hand-copied (see **Generated files**
below); `tests/test_mobile_contract.py` fails on drift. Desktop/web UI still
belongs in Electron only.

# Agent Rules — VoiceStudio

Binding for every AI agent (Claude, Codex, Cursor, review bots, …). CLAUDE.md is the full constitution; this is the operating contract. When they conflict, CLAUDE.md wins.

## Where things live

| Path | Role |
|---|---|
| `backend/` | FastAPI server, entry `backend/main.py` (`main:app` with `cd backend`, or `backend.main:app` from the root). Routes `api/`, services `services/`, lazy engine modules `engines/<name>` registered in `services/tts_backend.py`, tests `backend/tests/`. |
| `electron/` | The app: `src/main/` (backend supervisor, `app://` protocol + `/api` proxy, IPC), `src/preload/`, `src/renderer/src/{routes,features,components}`, `src/shared/` (legacy, being retired #2603 — never add new UI there). |
| `omnivoice/` | Python TTS model package (Apache-2.0 upstream, bundled). |
| `native/desktop-bridge/` | Rust helper Electron builds; `cargo fmt` before committing. |
| `mobile/` | Native iOS/Android apps + the shared contract and generated artifacts. |
| `tests/` | Repo-wide pytest suite (pytest `testpaths`); `tests/frontend/` is Node `node:test` for the JS build/dev scripts. |
| `electron/tests/` | Vitest specs, locale/packaging checks, Playwright desktop-UI and renderer smokes. |
| `scripts/` | Dev, build, release and CI helpers (also `export_openapi.py`, `export-mobile-tokens.ts`, `check-docs-drift.py`). |
| `config/app.json` | Product name, app ID and ports — backend 3900, web 3901, Electron dev 3902. Change here, not in launchers. |
| `frontend/` | Build output only: `bun run build:web` writes `frontend/dist`, which the backend serves at `/` (`OMNIVOICE_FRONTEND_DIST` overrides). No source code lives there. |

## Commands

Prereqs: Node **22** (`.nvmrc`; newer majors change error messages and fail tests that pass in CI), Bun `1.4.2` (`packageManager`), uv + Python 3.11+, ffmpeg. Linux desktop dev also needs the apt packages listed in `.github/CONTRIBUTING.md` → Prerequisites.

- `bun run dev` — Electron + supervised backend with HMR; first runs install JS and (unless an external backend is configured or on an Intel Mac) Python deps.
- `bun run setup:api` — rebuild only the Python environment.
- `bun run dev:web` — backend `:3900` + browser renderer `:3901`.
- `bun run dev:api` — backend only. Never start a second backend while the Electron supervisor runs one (it attaches to `127.0.0.1:3900`).
- `bun run build`, `bun run start`, `bun run dist` — build, run the built app, package locally (`--publish never`).
- CPU-only wheels: `OMNIVOICE_TORCH_VARIANT=cpu bun run setup:api`; direct uv: `uv sync --no-group cuda --group cpu`, then `uv run --no-sync ...`. Plain `uv sync` is the CUDA default on Linux/Windows.
- Clean state: `bun clean --dry-run` then `bun clean` (deletes app data/voices too; read the preview).

## Tests and gates

CI gate is the single required check `Tests (backend + frontend)`, which waits on every job in `ci.yml`.

- `uv run pytest tests/ -q -n auto`
- `uv run pytest backend/tests/ -q` — its own session/conftest; CI runs the two suites separately.
- One test: `uv run pytest tests/test_app_version.py -q`
- Set `HF_HUB_OFFLINE=1` and an empty `HF_HUB_CACHE` when touching download-gated code: CI runs offline, and a warm developer cache hides failures.
- `bun run test:frontend` — `node --test tests/frontend/*.test.mjs`.
- `bun run typecheck`, `bun run lint` (oxlint via `vp`), `bun run --cwd electron locale:check`.
- `bun run check:electron` — typecheck, tests, build, web build and packaging contract (the broad desktop gate).
- Desktop UI: `bun run --cwd electron build` then `bun run --cwd electron test:desktop-ui` (prefix `xvfb-run -a` on headless Linux; traces land in `electron/test-results/`).
- Rust change: `cargo check --manifest-path native/desktop-bridge/Cargo.toml`.

## Generated files (regenerate, never hand-edit)

- `bun scripts/export-mobile-tokens.ts` — mobile theme from the Electron theme.
- `uv run python scripts/export_openapi.py` — mobile API types from the backend.
- Mobile strings come from the Electron locale catalogs; `tests/test_mobile_contract.py` fails on drift.
- `python scripts/check-docs-drift.py` (daily CI) flags engine ids missing from `docs/features.yaml`; add a new engine id there in the same PR.
- DB schema changes need an alembic migration in `backend/migrations/` (root `alembic.ini` points at it) with a tested upgrade path; existing `omnivoice_data/` must keep working untouched.

## Wiring facts agents guess wrong

- The renderer never fetches `127.0.0.1:3900` directly: it calls app-relative `/api/...` (dev server proxy; in production the renderer is served from `app://voicestudio/` and main proxies with `net.fetch`). Do not add CORS workarounds.
- Backend modules use bare imports (`from core.config import ...`); `backend/main.py` puts `backend/` on `sys.path`. Backend tests set a hermetic `OMNIVOICE_DATA_DIR`.
- The supervisor attaches to a running backend, otherwise spawns `.venv` Python and supervises it; the child's stdin is its liveness signal (exit code 78 = port in use). Env knobs (`OMNIVOICE_PORT`, `OMNIVOICE_UI_PORT`, `VOICESTUDIO_SKIP_BACKEND`, `OMNIVOICE_STARTUP_BUDGET_S`, …) are in `electron/README.md`.
- Root `package.json` is the version source of truth; `pyproject.toml` and `backend/core/version.py` (`_FALLBACK_VERSION`) are lockstep mirrors (CI-backed by `tests/test_app_version.py`). Never bump unless the owner asks.
- Frontend files stay modular: soft 300 / hard 500 lines per `.jsx`/`.tsx`, one component per file, co-located `*.test.tsx`; pages are thin orchestrators. Enforced in review, not lint.

## Token economy (owner directive, 2026-07-20; tightened 2026-07-28)
- **Default to the shortest response that fully answers.** Outlines and tables over prose; no preamble, no recap of what you just did, no re-explaining a fix the diff already shows. Applies to every response, not just status updates.
- Lead with the outcome. No narration, no restating diffs, no filler praise, no plans you're about to execute anyway.
- Status updates: one line. Final reports: only what changes the reader's next action.
- Don't re-derive what CI, linters, or review bots already computed — read their output first (`gh pr checks`, bot comments via `gh api .../pulls/N/comments`).
- Mechanical rules live in deterministic tests, never in agent effort: changelog style (`tests/test_changelog_style.py`), locale parity (`tests/test_locale_parity.py`), version lockstep (`tests/test_app_version.py`), CJK (`tests/test_no_hardcoded_cjk.py`).
- Run targeted tests while iterating; full suites only before landing.

## Cross-platform parity: behaviour, not performance
- The parity rule covers user-visible BEHAVIOUR. Hardware acceleration varies by host by design (CUDA/MPS/DirectML, Triton availability, `torch.compile`); skipping an optimization where it physically cannot work is not a parity violation.
- Do not "fix" a parity finding by disabling a working optimization everywhere. That trades a real regression for a semantic one.
- A feature the user can see and use on one OS but not another IS a violation. Judge by what the user can do, not by how fast it runs.

## Merge protocol (hard rules)
1. Never merge without review. Harvest CodeRabbit + Greptile comments first; never merge with an unread Critical/P1.
2. Never accept a PR as-is: fix findings ON the PR branch pre-merge (maintainer commits fine; credit contributors in the changelog fragment). No merge-then-fix, no comment-and-walk-away.
3. Merge current `main` into stale branches before judging their CI — PR-green under an old workflow ≠ main-green.
4. Gate: "Tests (backend + frontend)" green + MERGEABLE.
5. After EVERY merge: watch `main`'s own post-merge runs to green (`gh run list --branch main`). Red main = drop everything and fix.
6. Start every PR, fix and feature from freshly fetched `origin/main` (owner rule, 2026-10-26): `git fetch origin`, confirm local `main` has no incoming or outgoing commits (resolve first if it does), branch from `origin/main`, and merge the latest `main` again right before pushing. `main` requires branches to be up to date before merging; that setting stays on.

Documentation/test-only CI policy (owner-set 2026-10-31): skip runtime tests and
product builds for documentation-only or test-only changes. Keep the required
check green through an explicit detected skip; run changed tests locally. Mixed
runtime/config/dependency changes still run CI, as do bundled app assets and
licence/catalog data. CLA, identity and secret checks remain enabled.

## Change rules (see CLAUDE.md for full text)
- Root-cause the class, not the instance; fail-before/pass-after regression test; smallest correct change. Never run a formatter across untouched files (no formatting churn).
- Default behavior identical on macOS/Windows/Linux; platform-only features go behind explicit opt-in. Divergent default = P0.
- Local-first: no new required network calls; any HF download gated on installed-ness or explicit user action; all synthetic audio through the `mark_synthetic` chokepoint. The exhaustive, owner-approved list of sanctioned calls lives in `.github/CONTRIBUTING.md` → Quality gates (Local-first); adding one needs owner approval.
- Every user-facing string via i18n, present in every file of `electron/src/renderer/src/i18n/locales/` (en + 21 translations) with real translations; `tests/test_locale_parity.py` and Electron `locale:check` enforce it. No hardcoded CJK outside the `tests/test_no_hardcoded_cjk.py` allowlist.
- Docs-sync in the same PR. Changelog: one quiet one-liner per PR in `changelog.d/<PR#>.<type>.md` (not `CHANGELOG.md`), ending `(#N)` + `— thanks @user!` for community work; the release script folds fragments into Unreleased.
- Tagged release announcements lead with the biggest user-visible change; redesigns need real UI screenshots and migrations need installer links and steps. Verify all contributor credits from the tag comparison and included PRs; list authors and bug reporters separately (see `docs/RELEASING.md`).
- JavaScript dependency changes require regenerating root `bun.lock` (Docker runs `--frozen-lockfile`); Python deps stay pinned in `uv.lock`.
- Attribution: commits, PR descriptions and comments carry only the submitter's git identity. Never credit an agent (no agent `Co-authored-by:`, "Generated with …", session links) and never add other names/emails. Human co-authors are fine. Enforced by the `commit-identity` check.
- Issues: absorb or decline — never defer to a future version. Check the open-PR queue before implementing community-reported fixes.

### Diagnostic app intake (owner task, 2026-11-15)

Separately opted-in automatic failure reports may replace the public events
request with `/api/public/v1/app-events` on the sanctioned Supermetry hosts
`https://app.supermetry.com` (unconfigured host default) or
`https://app.voicestudio.sh` (the owner-configured packaged app intake, owner-set
2026-11-16). App ID and write-only ingest key come only from
runtime environment or git-ignored build metadata. Release CI must use GitHub
Actions Secrets for the app ID and ingest key, never public repository variables,
and must not log their values; fork builds receive no upstream credentials.
`SUPERMETRY_APP_HOST` is an
explicit operator override, unset by default; any other production host must
be recorded and approved by the owner. This changes no product analytics or
collection permission. `diagnostics.sessionPings` is default off, requires the
same separate consent, and is never enabled in release workflow defaults.

## Shared select controls

- Use `electron/src/shared/components/SearchableSelect.jsx` for all new or redesigned select boxes. Reuse `VoiceSelector` for voice choices. Do not introduce native `<select>` controls.
- Provide a localized `ariaLabel`; use `menuPortal` inside scrolling or clipping containers. Preserve keyboard selection and disabled states.

## Agent skills

Project development skills are pinned in `skills-lock.json` and installed under
`.agents/skills/`: Vite and FastAPI. Load them for framework guidance; repository
rules and tracker mappings override generic skill guidance.

### Issue tracker

GitHub Issues on `debpalash/VoiceStudio`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `docs/adr/` plus a root `CONTEXT.md` that is created lazily and does not exist yet — skip it when absent. See `docs/agents/domain.md`.
