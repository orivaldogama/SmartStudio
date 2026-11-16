# VoiceStudio on Kaggle (2 × T4)

> **Status: plan, not shipped.** Nothing on this page works out of the box today.
> The dataset builder, the bootstrap notebook, read-only HF-cache support and
> licence pre-acceptance still have to land; see
> [Known gaps](#known-gaps-before-this-ships). The current position and the
> resume point for this work live in
> [the refactor timeline](../agents/kaggle-refactor-handoff.md).

Kaggle's free tier allocates two 16 GB NVIDIA Tesla T4 cards per session. That is
enough to run the Max model pack as a **remote backend**: the desktop app keeps
the UI, your voices and your exports; Kaggle does the inference.

This is a personal-use arrangement. Kaggle's [Terms of Use](https://www.kaggle.com/terms)
allow only personal, non-commercial use, and the platform is not a hosting
service — do not put a shared instance behind it.

## What this can and cannot do

| Capability | Works | Notes |
| --- | --- | --- |
| TTS, transcription, dubbing, translation on the T4s | Yes | Same engines as a local GPU host |
| Desktop app as the UI | Yes | **Settings → Sharing → Remote backend**: URL + API key |
| Browser-only UI | Yes | The backend serves the SPA at `/` when `frontend/dist` is present |
| Start the session from the app | **No** | Kaggle exposes no API for an interactive GPU session; a human clicks *Run* and the GPU is allocated then |
| Keep voices and exports between sessions | **No** | `/kaggle/working` only survives with *Save Version* (20 GB cap) |
| A stable URL | **No** | A quick tunnel gets a new hostname per session |
| Both T4s used | **Not yet** | The OSS backend is single-device; see [Known gaps](#known-gaps-before-this-ships) |

## Platform limits (free tier)

| Item | Limit |
| --- | --- |
| GPU | 2 × Tesla T4, 16 GB each (Turing, sm_75) |
| CPU / RAM | 4 vCPU / 29 GB |
| Session | 12 h, ends sooner when idle |
| GPU quota | About 30 h per week, shared |
| Saved working disk | 20 GB, only through *Save Version* |
| Dataset size | 200 GB per dataset |
| Inbound ports | None — reach the backend through a tunnel |
| Internet | On by default; a private dataset needs no credential at runtime |

T4-specific behaviour of the default engine (float16 only, no bf16, `sdpa`
attention, CUDA Graphs skipped below sm_80, ~2.5 GB peak) is measured in
[Tesla T4 notes](../hardware-notes-tesla-t4.md).

## Architecture

```
[private Kaggle dataset]   pre-populated Hugging Face cache (Max pack)
          | mounted read-only
          v
[Kaggle notebook session]  deps -> HF_HUB_CACHE -> OMNIVOICE_DATA_DIR=/kaggle/working
                           uvicorn 0.0.0.0:3900 + OMNIVOICE_API_KEY + tunnel
          | HTTPS
          v
[desktop VoiceStudio]      Settings -> Sharing -> Remote backend
```

## 1. Build the model dataset

The Max pack is five repositories, about 8.5 GB:

| Repository | Size | Role |
| --- | --- | --- |
| `k2-fsa/OmniVoice` | 2.4 GB | TTS |
| `Systran/faster-whisper-large-v3` | 2.9 GB | ASR |
| `csukuangfj/sherpa-onnx-whisper-tiny` | 0.104 GB | live dictation |
| `csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` | 0.67 GB | ASR |
| `facebook/nllb-200-distilled-600M` | 2.4 GB | translation |

Upload it as the **Hugging Face cache layout**, not as loose files:

```
/kaggle/input/voicestudio-models/hub/
  models--k2-fsa--OmniVoice/
    refs/main                          # file containing the snapshot commit
    snapshots/<commit>/...             # the files, unchanged
  models--Systran--faster-whisper-large-v3/
    ...
```

Two pieces of the backend depend on that shape:

- `backend/services/model_catalogue.py` reports a repository as installed by
  scanning the cache roots (`HF_HUB_CACHE`, then `HF_HOME`, then the default)
  for `models--<org>--<name>/snapshots/<revision>` with weights above a size
  floor. Loose files would be re-downloaded.
- `backend/services/hf_revisions.py` pins every curated repository to a reviewed
  commit SHA from `backend/config/model_licenses.json`. Build the dataset from
  `revision_for(repo_id)` so the snapshot directory the app looks for exists.

Ship a `manifest.json` next to the cache (`repo_id`, `revision`, `size_bytes`,
file count) so a mismatch is diagnosable instead of a silent re-download.

The builder script, the `scripts/` entry point and its test are part of the
[known gaps](#known-gaps-before-this-ships); they do not exist yet.

## 2. Bootstrap the backend in the session

Environment for the server process:

| Variable | Value | Why |
| --- | --- | --- |
| `OMNIVOICE_SERVER_MODE` | `1` | Server mode: the admin surface accepts the API key (Docker sets this too) |
| `OMNIVOICE_BIND_HOST` | `0.0.0.0` | Listen beyond loopback |
| `OMNIVOICE_API_KEY` | long random string | Bearer key for every non-loopback HTTP and WebSocket request |
| `HF_HUB_CACHE` | `/kaggle/input/voicestudio-models/hub` | Use the dataset instead of downloading |
| `HF_HUB_OFFLINE` | `1` | Fail fast instead of reaching the network |
| `OMNIVOICE_DATA_DIR` | `/kaggle/working/omnivoice` | Writable state (DB, voices, outputs) |
| `OMNIVOICE_FRONTEND_DIST` | path of the built SPA | Only needed for browser-only use |
| `OMNIVOICE_DEVICE` | `cuda` | Skip the probe's auto-detection |
| `OMNIVOICE_ALIGN_DEVICE` | `cuda` | WhisperX alignment uses wav2vec2 on CPU by default |
| `OMNIVOICE_GPU_WORKERS` | `1`–`2` | GPU pool threads; size it to free VRAM, not to the T4's 16 GB |

See [performance](../performance.md) for the full list and defaults.

The cache is mounted read-only, and the Hugging Face Hub writes into it
(`refs/`, lock files, `.incomplete`). Until read-only support lands, expect the
bootstrap to fail on a write; the workaround is a symlink overlay into
`/kaggle/working` and pointing `HF_HUB_CACHE` there.

Expose the port through a tunnel that dials out (Cloudflare Tunnel, ngrok). The
free quick tunnel changes hostname every session; a named tunnel on your own
domain is the only stable option.

## 3. Connect the desktop app

1. Start the backend and the tunnel, then open the tunnel URL's `/health` and
   confirm it answers 200.
2. **Settings → Sharing → Remote backend**: paste the `https://…` URL and the
   `OMNIVOICE_API_KEY` value, **Test connection**, then **Save & reload**.
3. If the tunnel dies, the app shows the remote-backend recovery screen; choose
   **Use local backend** until a new URL exists.

Plain `http://` on a tunnel sends the bearer key in clear text — use HTTPS. The
same key rules as any remote host apply; see [API authentication](../api-auth.md)
and [Sharing & remote access](../sharing.md).

## Licensing

Two of the five Max-pack repositories are non-commercial: NLLB-200 is CC-BY-NC
and OmniVoice's weights are non-commercial. Keep the dataset **private** and use
it yourself. See the [model licence inventory](../licensing/model-inventory.md).

Pre-installing the weights does not accept their terms: `services/model_acceptance.py`
still gates every model whose licence category is not `commercial`, so a fresh
session asks again. That gate is why licence pre-acceptance is in the gap list.

## Known gaps before this ships

| # | Gap | Where |
| --- | --- | --- |
| 1 | Read-only model cache (Hub wants `refs/`, locks, `.incomplete`) | `backend/services/model_catalogue.py`, Hub writes |
| 2 | Licence pre-acceptance for an ephemeral session | `backend/services/model_acceptance.py` |
| 3 | `frontend/dist` has to be published (built SPA, not in the dataset today) | `electron/vite.web.config.ts` |
| 4 | Dataset builder + manifest + test | `scripts/` (new) |
| 5 | Bootstrap notebook and this page's runbook | `notebooks/` (new) |
| 6 | Remote-backend URL changes per session | `electron/src/renderer/src/features/settings` (deep link/env) |
| 7 | Second T4 sits idle (single device per process) | `backend/services/model_manager.py`, `backend/core/device_caps.py` |

## Practical advice

- Do the first weight load before you need it: a cold download inside the
  generate budget is the classic "job exceeded 300 s" report from
  [Tesla T4 notes](../hardware-notes-tesla-t4.md).
- Dubbing is CPU-bound off the GPU (demucs, resampling) and 4 vCPU is the tight
  resource, not the T4.
- Treat `/kaggle/working` as scratch: export voices and finished audio to your
  desktop before the session ends.
- One session per week is cheaper than keeping one alive; the 30 h quota is shared
  across GPUs.
