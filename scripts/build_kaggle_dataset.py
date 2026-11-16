#!/usr/bin/env python3
"""Build the Kaggle model dataset for VoiceStudio (the Max model pack).

The dataset is a Hugging Face **hub cache** that VoiceStudio treats as already
installed: the backend scans ``HF_HUB_CACHE`` for
``models--<org>--<name>/snapshots/<revision>`` (``backend/services/model_catalogue.py``)
and repairs from ``refs/main`` / ``voicestudio-revision``
(``backend/services/hf_revisions.py``). Loose files would be re-downloaded.

Output layout, under ``--out``::

    hub/
      models--k2-fsa--OmniVoice/
        refs/main                     # the pinned commit, ASCII
        voicestudio-revision          # the same commit (VoiceStudio's marker)
        snapshots/<commit>/...        # real files, no symlinks, no blobs/
    manifest.json                     # repo ids, SHAs, sizes, per-file sha256
    dataset-metadata.json             # ready for `kaggle datasets create -p`
    README.md

Real copies instead of ``blobs/`` + symlinks keep the dataset usable from a
read-only mount (``/kaggle/input``) and safe to unzip: a zip does not preserve
symlinks, so a link-based cache would arrive broken.

Revisions come from :func:`services.hf_revisions.revision_for`, the same reviewed
pins the app downloads. Nothing here contacts the network unless ``--download``
is passed (local-first: a download is an explicit action).

    python scripts/build_kaggle_dataset.py --out build/kaggle-max
    python scripts/build_kaggle_dataset.py --out build/kaggle-max --download
    python scripts/build_kaggle_dataset.py --out build/kaggle-max --owner <you>
    kaggle datasets create -p build/kaggle-max        # after reviewing metadata

Non-commercial: NLLB-200 (CC-BY-NC) and OmniVoice's weights are non-commercial,
so keep the dataset private and use it yourself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

#: The Max model pack (electron/src/renderer/src/features/settings/performance-model-packs.ts).
#: tests/scripts/test_build_kaggle_dataset.py fails if this list drifts from it.
MAX_PACK_REPOS: tuple[str, ...] = (
    "k2-fsa/OmniVoice",
    "Systran/faster-whisper-large-v3",
    "csukuangfj/sherpa-onnx-whisper-tiny",
    "csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8",
    "facebook/nllb-200-distilled-600M",
)

SCHEMA = 1
#: Files the Hub writes for itself; never part of a snapshot payload.
_SKIP_NAMES = frozenset({".DS_Store", ".incomplete"})
_HASH_CHUNK = 1024 * 1024


class BuildError(RuntimeError):
    """A problem the person running the script can fix (missing cache, disk)."""


def repo_dir_name(repo_id: str) -> str:
    """``k2-fsa/OmniVoice`` -> ``models--k2-fsa--OmniVoice`` (the Hub's shape)."""
    return "models--" + repo_id.replace("/", "--")


def revision_for(repo_id: str) -> str:
    """The reviewed commit for ``repo_id``, resolved by the backend itself."""
    backend = Path(__file__).resolve().parents[1] / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services.hf_revisions import revision_for as pinned  # noqa: PLC0415

    return pinned(repo_id)


def cache_roots() -> list[str]:
    """Candidate hub roots, in the order the backend probes them."""
    env = (os.environ.get("HF_HUB_CACHE") or "").strip()
    if env:
        return [env]
    base = (os.environ.get("HF_HOME") or "").strip()
    if base:
        return [os.path.join(base, "hub")]
    return [os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")]


def cached_snapshot(repo_id: str, revision: str, roots: list[str]) -> Path | None:
    """The existing local snapshot directory for ``repo_id`` at ``revision``."""
    relative = Path(repo_dir_name(repo_id)) / "snapshots" / revision
    for root in roots:
        candidate = Path(root) / relative
        if candidate.is_dir():
            return candidate
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_file(source: Path, target: Path) -> None:
    """Copy a snapshot entry as real bytes, resolving a blob symlink if present."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source.resolve(), target)


def materialise(repo_id: str, revision: str, source: Path, hub: Path) -> dict:
    """Copy one snapshot into ``hub`` and return its manifest entry."""
    repo_dir = hub / repo_dir_name(repo_id)
    snapshot = repo_dir / "snapshots" / revision
    if snapshot.exists():
        shutil.rmtree(snapshot)  # this directory is ours; rebuild it cleanly
    snapshot.mkdir(parents=True)

    files: list[dict] = []
    total = 0
    for path in sorted(source.rglob("*")):
        if path.is_dir() or path.name in _SKIP_NAMES:
            continue
        relative = path.relative_to(source).as_posix()
        target = snapshot / relative
        _copy_file(path, target)
        size = target.stat().st_size
        total += size
        files.append({"path": relative, "size_bytes": size})

    # refs/main is the fallback VoiceStudio and huggingface_hub both read;
    # voicestudio-revision is the marker newer installs look at first.
    refs = repo_dir / "refs"
    refs.mkdir(parents=True, exist_ok=True)
    (refs / "main").write_text(revision + "\n", encoding="ascii")
    (repo_dir / "voicestudio-revision").write_text(revision + "\n", encoding="ascii")

    return {
        "repo_id": repo_id,
        "revision": revision,
        "size_bytes": total,
        "file_count": len(files),
        "files": files,
    }


def add_hashes(entries: list[dict], hub: Path) -> None:
    """Fill in per-file sha256 plus a deterministic digest per repository."""
    for entry in entries:
        rewritten = []
        tree = hashlib.sha256()
        base = hub / repo_dir_name(entry["repo_id"]) / "snapshots" / entry["revision"]
        for item in entry["files"]:
            digest = sha256_file(base / item["path"])
            item["sha256"] = digest
            tree.update(item["path"].encode("utf-8"))
            tree.update(b"\0")
            tree.update(str(item["size_bytes"]).encode("ascii"))
            tree.update(b"\0")
            tree.update(digest.encode("ascii"))
            tree.update(b"\n")
            rewritten.append(item)
        entry["files"] = rewritten
        entry["digest"] = tree.hexdigest()


def download_snapshot(repo_id: str, revision: str) -> tuple[Path, tempfile.TemporaryDirectory]:
    """Fetch ``repo_id@revision`` into a throwaway cache and return its snapshot."""
    from huggingface_hub import snapshot_download  # noqa: PLC0415 - optional path

    holder = tempfile.TemporaryDirectory(prefix="voicestudio-kaggle-")
    cache = Path(holder.name) / "hub"
    path = snapshot_download(repo_id=repo_id, revision=revision, cache_dir=str(cache))
    return Path(path), holder


def dataset_readme(entry_count: int, total_bytes: int, generated: str) -> str:
    return (
        "# VoiceStudio model pack (Max)\n\n"
        "Hugging Face hub cache for the VoiceStudio Max model pack, intended to be\n"
        "mounted read-only at `/kaggle/input` and pointed at with `HF_HUB_CACHE`.\n\n"
        f"Built {generated}: {entry_count} repositories, "
        f"{total_bytes / (1024 ** 3):.2f} GiB.\n\n"
        "`manifest.json` records the reviewed commit SHA of every repository and a\n"
        "sha256 per file. `hub/` holds real files (no symlinks, no `blobs/`) so the\n"
        "dataset survives a zip round-trip and a read-only mount.\n\n"
        "## Licensing\n\n"
        "Non-commercial: NLLB-200 is CC-BY-NC and OmniVoice's weights are\n"
        "non-commercial. Keep this dataset private; do not redistribute the weights.\n"
    )


def dataset_metadata(owner: str | None) -> dict:
    slug = (owner or "your-username").strip().lower()
    return {
        "title": "VoiceStudio model pack (Max)",
        "id": f"{slug}/voicestudio-model-pack-max",
        "licenses": [{"name": "other"}],
        "description": (
            "Hugging Face hub cache for the VoiceStudio Max model pack "
            "(non-commercial weights). See manifest.json for pinned revisions."
        ),
    }


def build(out: Path, *, download: bool, hashes: bool, owner: str | None, force: bool) -> dict:
    if out.exists() and any(out.iterdir()) and not force:
        raise BuildError(
            f"{out} already exists and is not empty; pass --force to rebuild it"
        )
    out.mkdir(parents=True, exist_ok=True)
    hub = out / "hub"
    hub.mkdir(parents=True, exist_ok=True)

    roots = cache_roots()
    entries: list[dict] = []
    missing: list[str] = []
    holders: list[tempfile.TemporaryDirectory] = []
    try:
        for repo_id in MAX_PACK_REPOS:
            revision = revision_for(repo_id)
            source = cached_snapshot(repo_id, revision, roots)
            if source is None:
                if not download:
                    missing.append(f"{repo_id}@{revision}")
                    continue
                print(f"downloading {repo_id}@{revision[:12]} ...", flush=True)
                source, holder = download_snapshot(repo_id, revision)
                holders.append(holder)
            entry = materialise(repo_id, revision, source, hub)
            entries.append(entry)
            print(
                f"  {repo_id}: {entry['file_count']} files, "
                f"{entry['size_bytes'] / (1024 ** 3):.2f} GiB",
                flush=True,
            )
        if missing:
            raise BuildError(
                "no local snapshot for:\n  "
                + "\n  ".join(missing)
                + "\n\nInstall the Max pack in VoiceStudio first, or pass --download."
            )
    finally:
        for holder in holders:
            holder.cleanup()

    if hashes:
        print("hashing files ...", flush=True)
        add_hashes(entries, hub)

    total_bytes = sum(entry["size_bytes"] for entry in entries)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {
        "schema": SCHEMA,
        "generated_at": generated,
        "layout": "huggingface-hub-cache",
        "hub_dir": "hub",
        "total_bytes": total_bytes,
        "repos": entries,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "dataset-metadata.json").write_text(
        json.dumps(dataset_metadata(owner), indent=2) + "\n", encoding="utf-8"
    )
    (out / "README.md").write_text(
        dataset_readme(len(entries), total_bytes, generated), encoding="utf-8"
    )
    if owner is None:
        print(
            "warning: dataset-metadata.json has a placeholder owner; "
            "pass --owner <kaggle-username> before `kaggle datasets create`.",
            file=sys.stderr,
        )
    print(f"dataset ready: {out} ({total_bytes / (1024 ** 3):.2f} GiB)")
    return manifest


def write_zip(out: Path, *, compress: bool) -> Path:
    """Pack ``out`` into ``<out>.zip``; stored by default (weights barely deflate)."""
    archive = out.with_suffix(".zip")
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(archive, "w", compression=mode, compresslevel=1 if compress else None) as zf:
        for path in sorted(out.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out).as_posix())
    print(f"archive: {archive} ({archive.stat().st_size / (1024 ** 3):.2f} GiB)")
    return archive


def verify(out: Path, *, hashes: bool) -> int:
    """Check an existing dataset against its manifest. Returns a process code."""
    manifest_path = out / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {manifest_path}: {exc}", file=sys.stderr)
        return 2
    problems: list[str] = []
    for entry in manifest.get("repos", []):
        base = out / "hub" / repo_dir_name(entry["repo_id"]) / "snapshots" / entry["revision"]
        marker = out / "hub" / repo_dir_name(entry["repo_id"]) / "refs" / "main"
        if not base.is_dir():
            problems.append(f"missing snapshot {entry['repo_id']}")
            continue
        if not marker.is_file() or marker.read_text(encoding="ascii").strip() != entry["revision"]:
            problems.append(f"refs/main mismatch {entry['repo_id']}")
        for item in entry["files"]:
            target = base / item["path"]
            if not target.is_file():
                problems.append(f"missing file {entry['repo_id']}/{item['path']}")
                continue
            if target.stat().st_size != item["size_bytes"]:
                problems.append(f"size mismatch {entry['repo_id']}/{item['path']}")
                continue
            if hashes and "sha256" in item and sha256_file(target) != item["sha256"]:
                problems.append(f"hash mismatch {entry['repo_id']}/{item['path']}")
    for problem in problems[:50]:
        print(problem, file=sys.stderr)
    if problems:
        print(f"{len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"ok: {len(manifest.get('repos', []))} repositories match the manifest")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build-kaggle-dataset",
        description=(
            "Materialise the VoiceStudio Max model pack as a Hugging Face hub "
            "cache dataset for Kaggle."
        ),
        epilog=(
            "Run --download to fetch missing repositories, then "
            "`kaggle datasets create -p <out>`. See docs/install/kaggle.md."
        ),
    )
    parser.add_argument("--out", type=Path, default=Path("build/kaggle-max"),
                        help="output directory (default: build/kaggle-max)")
    parser.add_argument("--download", action="store_true",
                        help="download missing repositories instead of failing")
    parser.add_argument("--no-hashes", dest="hashes", action="store_false",
                        help="skip the per-file sha256 pass (faster, weaker manifest)")
    parser.add_argument("--zip", action="store_true", help="also write <out>.zip")
    parser.add_argument("--compress", action="store_true",
                        help="deflate the archive (slower; weights barely compress)")
    parser.add_argument("--owner", default=None,
                        help="Kaggle username for dataset-metadata.json")
    parser.add_argument("--force", action="store_true", help="rebuild a non-empty --out")
    parser.add_argument("--verify", action="store_true",
                        help="verify --out against its manifest and exit")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            return verify(args.out, hashes=args.hashes)
        build(args.out, download=args.download, hashes=args.hashes,
              owner=args.owner, force=args.force)
        if args.zip:
            write_zip(args.out, compress=args.compress)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
