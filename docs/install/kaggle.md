# VoiceStudio on Kaggle (2 × T4)

> **Status: built, not yet run on Kaggle.** The dataset builder
> (`scripts/build_kaggle_dataset.py`) and the bootstrap notebook
> (`notebooks/VoiceStudio_Kaggle_2xT4.ipynb`) exist; neither has been exercised
> on a live 2 × T4 session. The gaps that remain are listed in
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
| Stop the session from the app | **Yes** | **Settings → Sharing → Remote backend → Shut down session**: the notebook's control route stops the tunnel and ends the kernel, so Kaggle releases the GPU instead of idling until the timeout |
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
          | mounted read-only at /kaggle/input
          v
[Kaggle notebook session]  deps -> HF_HUB_CACHE -> OMNIVOICE_DATA_DIR=/kaggle/working
                           uvicorn 127.0.0.1:3900 + OMNIVOICE_API_KEY
                           cloudflared quick tunnel (dials out)
          | HTTPS
          v
[desktop VoiceStudio]      Settings -> Sharing -> Remote backend
```

## Runbook

1. Build the dataset on a machine that already has the Max pack installed
   (section 1), and upload it privately.
2. Attach it to a Kaggle notebook with **GPU T4 ×2** and run
   `notebooks/VoiceStudio_Kaggle_2xT4.ipynb` (section 2).
3. Paste the URL and API key it prints into the desktop app (section 3).

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
/kaggle/input/voicestudio-model-pack-max/
  hub/
    models--k2-fsa--OmniVoice/
      refs/main                        # file containing the snapshot commit
      voicestudio-revision             # the same commit, VoiceStudio's marker
      snapshots/<commit>/...           # the files, unchanged
    models--Systran--faster-whisper-large-v3/
      ...
  manifest.json                        # repo ids, SHAs, sizes, file hashes
  dataset-metadata.json                # the file `kaggle datasets create -p` reads
```

Two pieces of the backend depend on that shape:

- `backend/services/model_catalogue.py` reports a repository as installed by
  scanning the cache roots (`HF_HUB_CACHE`, then `HF_HOME`, then the default)
  for `models--<org>--<name>/snapshots/<revision>` with weights above a size
  floor. Loose files would be re-downloaded.
- `backend/services/hf_revisions.py` pins every curated repository to a reviewed
  commit SHA from `backend/config/model_licenses.json`. The snapshot directory
  the app looks for is `revision_for(repo_id)`'s, so build from that.

`scripts/build_kaggle_dataset.py` does all of it:

```sh
# On a machine whose VoiceStudio already has the Max pack installed:
uv run python scripts/build_kaggle_dataset.py --out build/kaggle-max --owner <your-kaggle-username>

# Or let it fetch the five repositories itself (network, several GB):
uv run python scripts/build_kaggle_dataset.py --out build/kaggle-max --download --owner <name>

# Re-check an output against its manifest (sizes always, sha256 by default):
uv run python scripts/build_kaggle_dataset.py --out build/kaggle-max --verify

kaggle datasets create -p build/kaggle-max
# Rebuilding: bump nothing, re-run the builder, then
# kaggle datasets version -p build/kaggle-max -m "rebuild at the same pins"
```

What lands in `--out`:

| Path | Contents |
| --- | --- |
| `hub/` | The cache layout above, as **real files** — no `blobs/`, no symlinks, so a zip round-trip and a read-only mount both work |
| `manifest.json` | `repo_id`, pinned `revision`, `size_bytes`, `file_count`, per-file `sha256`, and one `digest` per repository |
| `dataset-metadata.json` | Title, id and licence, ready for `kaggle datasets create -p` |
| `README.md` | What the dataset is and its non-commercial terms |

The builder never touches the network unless `--download` is passed, and it
refuses a non-empty `--out` without `--force`. `tests/scripts/test_build_kaggle_dataset.py`
checks the result through the backend's own readers (`model_catalogue`,
`hf_revisions`), not a re-implementation of the layout rule.

## 2. Bootstrap the backend in the session

`notebooks/VoiceStudio_Kaggle_2xT4.ipynb` is the runnable form of this section.
Attach the dataset, pick **Settings → Accelerator → GPU T4 ×2**, keep internet
on, and run the cells: it locates the mounted `hub/`, installs the backend the
way the Docker image does (`uv pip install --system` with
`deploy/torch-constraints.txt`, `deploy/security-constraints.txt` and
`deploy/uv-overrides.txt`), side-loads cuDNN 8 for CTranslate2, records your
per-session licence acceptance for the pack (see [Licensing](#licensing)),
starts uvicorn, waits for `/health`, checks the five repositories through
`/models` and prints the tunnel URL with the API key.

The start cell launches uvicorn through a small `session_control.py` sidecar it
writes next to the log: the backend app plus one extra route,
`POST /api/session-control/shutdown`, behind the same Bearer gate as every
other remote request. Called from the desktop app (section 3), it stops the
tunnel, ends the notebook kernel — which ends the Kaggle session and its GPU
billing — and exits the server. `tests/test_kaggle_session_control.py` pins the
contract; the Kaggle side of it has not been exercised live yet (gap 6).

Environment for the server process:

| Variable | Value | Why |
| --- | --- | --- |
| `OMNIVOICE_SERVER_MODE` | `1` | Server mode: the admin surface accepts the API key (Docker sets this too) |
| `OMNIVOICE_API_KEY` | long random string | Bearer key for every non-loopback HTTP and WebSocket request |
| `OMNIVOICE_BIND_HOST` | unset (loopback) | The tunnel runs on the same host; set `0.0.0.0` only when the proxy is elsewhere |
| `HF_HUB_CACHE` | `/kaggle/input/<dataset-slug>/hub` | Use the dataset instead of downloading |
| `HF_HUB_OFFLINE` | `1` | Fail fast instead of reaching the network |
| `OMNIVOICE_DATA_DIR` | `/kaggle/working/omnivoice` | Writable state (DB, voices, outputs) |
| `OMNIVOICE_FRONTEND_DIST` | path of the built SPA | Only needed for browser-only use |
| `OMNIVOICE_DEVICE` | `cuda` | Skip the probe's auto-detection |
| `OMNIVOICE_ALIGN_DEVICE` | `cuda` | WhisperX alignment uses wav2vec2 on CPU by default |
| `OMNIVOICE_GPU_WORKERS` | `1`–`2` | GPU pool threads; size it to free VRAM, not to the T4's 16 GB |

See [performance](../performance.md) for the full list and defaults.

The cache is mounted read-only and the load path does not write to it: under
`HF_HUB_OFFLINE=1` the repair pass in `services/hf_cache_repair.py` skips
entirely, `snapshot_download(…, local_files_only=True)` only reads, and the
`voicestudio-revision` marker the backend writes after a real download is
already in the dataset. That argument has not yet been proven against a live
mount — see gap 1.

Expose the port through a tunnel that dials out (Cloudflare Tunnel, ngrok). The
free quick tunnel changes hostname every session; a named tunnel on your own
domain is the only stable option.

## 3. Connect the desktop app

1. The tunnel cell prints the URL and the API key; it also writes them to
   `/kaggle/working/remote-backend.txt`, which does not survive the session.
2. Open the tunnel URL's `/health` and confirm it answers. Any HTTP status means
   the tunnel reaches the backend.
3. **Settings → Sharing → Remote backend**: paste the `https://…` URL and the
   `OMNIVOICE_API_KEY` value, **Test connection**, then **Save & reload**.
4. If the tunnel dies, the app shows the remote-backend recovery screen; choose
   **Use local backend** until a new URL exists.
5. When you are done, press **Shut down session** in the same panel (and confirm):
   the control route ends the tunnel and the kernel, so the GPU quota stops at
   once instead of running down the idle timeout. Starting again stays manual —
   a human clicks *Run* — and the next session prints a new URL.

The desktop app sends the key on every request, so the backend's `Host` check
never applies to it. A **browser** does carry `Origin`, so browser-only use needs
that hostname in `OMNIVOICE_ALLOWED_ORIGINS` and `OMNIVOICE_ALLOWED_HOSTS`, plus
`frontend/dist` present.

Plain `http://` on a tunnel sends the bearer key in clear text — use HTTPS. The
same key rules as any remote host apply; see [API authentication](../api-auth.md)
and [Sharing & remote access](../sharing.md).

## Licensing

Two of the five Max-pack repositories are non-commercial: NLLB-200 is CC-BY-NC
and OmniVoice's weights are non-commercial. Keep the dataset **private** and use
it yourself. See the [model licence inventory](../licensing/model-inventory.md).

Pre-installing the weights does not accept their terms: `services/model_acceptance.py`
still gates every model whose licence category is not `commercial`, and acceptance is
recorded in `OMNIVOICE_DATA_DIR` — which is ephemeral, so every fresh session must
record it again. The bootstrap notebook has an explicit licence cell for that: it
runs `scripts/kaggle_preaccept_licenses.py`, which records acceptance for the pack
through the same fingerprinted `accept()` call the app UI uses (terms that change
later still ask again) and refuses to run without `OMNIVOICE_DATA_DIR` set, so it
can never touch a real profile by accident. Running the cell is your acceptance act
for the session; skip it and the app asks per model in the UI instead.

## Known gaps before this ships

| # | Gap | Where |
| --- | --- | --- |
| 1 | Read-only cache is argued, not proven: a live mount has not been exercised, and any path that still writes would fail there | `backend/services/model_catalogue.py`, Hub writes |
| 2 | ~~Licence pre-acceptance for an ephemeral session~~ **closed in code**: the notebook's licence cell runs `scripts/kaggle_preaccept_licenses.py` (not yet exercised live) | `scripts/kaggle_preaccept_licenses.py` |
| 3 | `frontend/dist` has to be published for browser-only use (optional: the desktop app needs nothing) | `electron/vite.web.config.ts` |
| 4 | Remote-backend URL changes per session | `electron/src/renderer/src/features/settings` (deep link/env) |
| 5 | Second T4 sits idle (single device per process) | `backend/services/model_manager.py`, `backend/core/device_caps.py` |
| 6 | No live-session run: install timings, first-load time and the T4 wheel behaviour are unmeasured | `notebooks/VoiceStudio_Kaggle_2xT4.ipynb` |

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
