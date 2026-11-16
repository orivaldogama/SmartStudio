<div align="center">

# SmartStudio

**AI voice studio — local-first, with a free Kaggle GPU as the engine room.**

Personal, non-commercial fork of [VoiceStudio](https://github.com/debpalash/VoiceStudio) · private use only · not distributed

</div>

> [!NOTE]
> SmartStudio is one owner's private fork of [VoiceStudio](https://github.com/debpalash/VoiceStudio) (AGPL-3.0), refactored to run the heavy inference on Kaggle's free 2 × T4 tier instead of commercial cloud or store channels. This page replaces the upstream README: no installers, sponsors, Pro/Cloud offers or marketing badges. Inherited guides under `docs/` and the app UI itself still carry the VoiceStudio name in places.

## What this fork changes

**Remote GPU backend on Kaggle (2 × Tesla T4, free tier).** The desktop app keeps the UI, voices, projects and exports; a Kaggle notebook session runs the engines:

| Piece | Role |
| --- | --- |
| [scripts/build_kaggle_dataset.py](scripts/build_kaggle_dataset.py) | Packs the Max model pack (~8.5 GB, 5 Hugging Face repos) into a private Kaggle dataset — a pre-populated HF cache, mounted read-only |
| [notebooks/VoiceStudio_Kaggle_2xT4.ipynb](notebooks/VoiceStudio_Kaggle_2xT4.ipynb) | Bootstraps the backend in a Kaggle GPU session: deps → `HF_HUB_CACHE` → `OMNIVOICE_DATA_DIR=/kaggle/working` → uvicorn on `127.0.0.1:3900` + `OMNIVOICE_API_KEY` → cloudflared quick tunnel |
| Desktop app | Connects via **Settings → Sharing → Remote backend** (tunnel URL + API key) |

```text
[private Kaggle dataset]   pre-populated HF cache (Max pack)
          │ mounted read-only at /kaggle/input
[Kaggle 2 × T4 session]    uvicorn 127.0.0.1:3900 + API key → cloudflared quick tunnel
          │ HTTPS
[desktop app]              Settings → Sharing → Remote backend
```

- Runbook, platform limits and known gaps: [docs/install/kaggle.md](docs/install/kaggle.md)
- Decisions, commit ledger and resume point: [docs/agents/kaggle-refactor-handoff.md](docs/agents/kaggle-refactor-handoff.md)
- Measured T4 behaviour of the default engine: [docs/hardware-notes-tesla-t4.md](docs/hardware-notes-tesla-t4.md)

Status: builder and notebook are committed but **have not run on a live Kaggle session yet**; the multi-GPU (second T4) refactor is scheduled last. Sessions are ephemeral by decision — nothing survives one. Kaggle's free tier permits only personal, non-commercial use, which is exactly this fork's scope.

## What you can do (inherited)

Voice cloning, voice design, video dubbing, dictation and transcription, audiobooks and long-form narration, batch jobs, local API and MCP — 646 languages, running on CUDA/MPS/ROCm/CPU locally or on the remote backend above. Full inventory: [features & engine catalog](docs/feature-catalog.md) · guide index: [docs/README.md](docs/README.md).

## Platforms

- **Local backend:** macOS (Apple Silicon), Windows x64, Linux x64 — CUDA, MPS, opt-in Windows ROCm, Vulkan for supported GGUF engines, or CPU-only. Intel Macs are limited to the app UI with a remote backend.
- **Remote backend:** any host running the FastAPI server, including the Kaggle 2 × T4 session (no inbound ports, no stable URL, ~30 h/week shared GPU quota, 12 h sessions).
- **No installers here:** this fork runs from source or from a local `bun run dist` build. Upstream installers, stores and Docker images ship upstream VoiceStudio, not this fork.
- `mobile/` (iOS/Android) is inherited and not a focus of this fork.

## Get started

Prereqs: Node 22 (`.nvmrc`), Bun, uv + Python 3.11+, ffmpeg; Rust/Cargo for `native/desktop-bridge`.

```bash
bun run dev          # Electron + supervised local backend, hot reload
bun run dev:web      # backend :3900 + renderer in a browser :3901
bun run dist         # package locally, no publish
```

Kaggle remote backend: build the private dataset, run the notebook, paste the tunnel URL and API key into **Settings → Sharing → Remote backend** — step by step in [docs/install/kaggle.md](docs/install/kaggle.md).

Inherited agent skills for Claude Code/Codex/Cursor: `npx skills add debpalash/VoiceStudio` (**voicestudio** for audio work, **voicestudio-maintainer** for the repo); agent-driven install guide: [docs/install/agent.md](docs/install/agent.md).

## Development

```bash
uv run pytest tests/ -q -n auto    # repo-wide suite
uv run pytest backend/tests/ -q    # backend suite (separate session)
bun run check:electron             # typecheck + Electron tests + builds + packaging contract
bun run lint                       # oxlint
```

Architecture, hard rules and conventions: [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md). Upstream contribution flow, including the CLA ([sign it before a first PR](.github/CONTRIBUTING.md#contribution-licensing)): [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md). Fork workflow (commit ledger, push rules, decisions): [handoff timeline](docs/agents/kaggle-refactor-handoff.md).

## License & responsible use

SmartStudio is a fork of [VoiceStudio](https://github.com/debpalash/VoiceStudio) by Palash Debnath and its contributors, licensed [AGPL-3.0](LICENSE) — see [LICENSE-NOTICE.md](LICENSE-NOTICE.md). This fork is maintained for the private, non-commercial use of its owner and is not distributed; any distribution would carry the full AGPL-3.0 obligations. Model weights, voices and generated output have their own licences, shown per model in the Model Manager.

Clone a voice only with its owner's permission. Unauthorized voice cloning, impersonation, fraud or scams are prohibited; compliance with applicable laws and ethical standards rests entirely with the user.

Upstream project — releases, bug reports, community: [github.com/debpalash/VoiceStudio](https://github.com/debpalash/VoiceStudio) · [Discord](https://discord.gg/bzQavDfVV9)
