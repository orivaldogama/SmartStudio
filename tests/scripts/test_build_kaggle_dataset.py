"""Tests for scripts/build_kaggle_dataset.py.

The point of the builder is a cache the *backend* accepts, so the assertions go
through the backend's own readers (``model_catalogue``, ``hf_revisions``) rather
than re-implementing the layout check here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
for entry in (str(ROOT), str(BACKEND)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from scripts import build_kaggle_dataset as builder  # noqa: E402
from services import hf_revisions, model_catalogue  # noqa: E402

REPO = "k2-fsa/OmniVoice"
WEIGHT = b"\0" * (5 * 1024 * 1024 + 1024)  # above snapshot_has_weights' floor


def _seed_cache(root: Path, repo_id: str, revision: str) -> Path:
    """A minimal but *complete* snapshot: one weight file plus a config."""
    snapshot = root / builder.repo_dir_name(repo_id) / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").write_bytes(WEIGHT)
    (snapshot / "config.json").write_text('{"model_type": "omnivoice"}', encoding="utf-8")
    return snapshot


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    revision = hf_revisions.revision_for(REPO)
    hub = tmp_path / "cache" / "hub"
    _seed_cache(hub, REPO, revision)
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setattr(builder, "MAX_PACK_REPOS", (REPO,))
    return hub, revision


def test_max_pack_matches_the_renderer_constant() -> None:
    """The script must never build a pack the app does not ask for."""
    source = (
        ROOT / "electron/src/renderer/src/features/settings/performance-model-packs.ts"
    ).read_text(encoding="utf-8")
    constants = dict(re.findall(r"const (\w+) = '([^']+)';", source))
    block = re.search(r"max:\s*\[([^\]]*)\]", source)
    assert block is not None, "performancePackRepos.max not found"
    names = [name.strip() for name in block.group(1).split(",") if name.strip()]
    renderer = tuple(constants.get(name, name) for name in names)
    assert builder.MAX_PACK_REPOS == renderer


def test_build_produces_a_cache_the_backend_accepts(
    tmp_path: Path, cache: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _hub, revision = cache
    out = tmp_path / "dataset"

    manifest = builder.build(
        out, download=False, hashes=True, owner="tester", force=False
    )

    snapshot = out / "hub" / builder.repo_dir_name(REPO) / "snapshots" / revision
    repo_dir = out / "hub" / builder.repo_dir_name(REPO)
    assert (snapshot / "model.safetensors").read_bytes() == WEIGHT
    assert (repo_dir / "refs" / "main").read_text(encoding="ascii").strip() == revision
    assert (repo_dir / "voicestudio-revision").read_text(encoding="ascii").strip() == revision

    # Real files: a zip round-trip and a read-only mount both need that.
    assert not any(path.is_symlink() for path in (out / "hub").rglob("*"))
    assert not (repo_dir / "blobs").exists()

    [entry] = manifest["repos"]
    assert entry["repo_id"] == REPO
    assert entry["revision"] == revision
    assert entry["size_bytes"] == sum(item["size_bytes"] for item in entry["files"])
    hashed = {item["path"]: item["sha256"] for item in entry["files"]}
    assert hashed["model.safetensors"] == hashlib.sha256(WEIGHT).hexdigest()
    assert len(entry["digest"]) == 64

    # The backend's own readers must agree.
    monkeypatch.setenv("HF_HUB_CACHE", str(out / "hub"))
    model = model_catalogue.catalogue_entry(REPO)
    assert model is not None
    assert model_catalogue.snapshot_is_complete(model, str(snapshot))
    assert str(snapshot) in model_catalogue._snapshot_dirs(REPO)  # noqa: SLF001
    assert hf_revisions.installed_revision(REPO, str(out / "hub")) == revision

    assert builder.verify(out, hashes=True) == 0


def test_verify_reports_a_tampered_file(tmp_path: Path, cache: tuple[Path, str]) -> None:
    _hub, revision = cache
    out = tmp_path / "dataset"
    builder.build(out, download=False, hashes=True, owner=None, force=False)

    # Same byte length, different bytes: only the sha256 can catch this.
    target = out / "hub" / builder.repo_dir_name(REPO) / "snapshots" / revision / "config.json"
    original = target.read_text(encoding="utf-8")
    assert len(original) == len('{"model_type": "omnivoice"}')
    target.write_text('{"model_type": "0mnivoice"}', encoding="utf-8")
    assert builder.verify(out, hashes=True) == 1
    assert builder.verify(out, hashes=False) == 0


def test_missing_snapshot_names_the_repo_and_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty"))
    monkeypatch.setattr(builder, "MAX_PACK_REPOS", (REPO,))

    with pytest.raises(builder.BuildError) as raised:
        builder.build(tmp_path / "dataset", download=False, hashes=False,
                      owner=None, force=False)
    message = str(raised.value)
    assert REPO in message
    assert "--download" in message


def test_refuses_to_overwrite_without_force(
    tmp_path: Path, cache: tuple[Path, str]
) -> None:
    out = tmp_path / "dataset"
    builder.build(out, download=False, hashes=False, owner=None, force=False)
    with pytest.raises(builder.BuildError, match="--force"):
        builder.build(out, download=False, hashes=False, owner=None, force=False)


def test_zip_keeps_the_cache_paths(tmp_path: Path, cache: tuple[Path, str]) -> None:
    _hub, revision = cache
    out = tmp_path / "dataset"
    builder.build(out, download=False, hashes=False, owner=None, force=False)

    archive = builder.write_zip(out, compress=False)
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert any(name.endswith(f"snapshots/{revision}/model.safetensors") for name in names)


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
def test_symlinked_snapshot_is_copied_as_real_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Hub stores snapshots as symlinks into blobs/; the dataset must not."""
    revision = hf_revisions.revision_for(REPO)
    hub = tmp_path / "cache" / "hub"
    blob = hub / builder.repo_dir_name(REPO) / "blobs" / "abc123"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(WEIGHT)
    snapshot = hub / builder.repo_dir_name(REPO) / "snapshots" / revision
    snapshot.mkdir(parents=True)
    (snapshot / "model.safetensors").symlink_to(blob)
    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    monkeypatch.setattr(builder, "MAX_PACK_REPOS", (REPO,))

    out = tmp_path / "dataset"
    builder.build(out, download=False, hashes=False, owner=None, force=False)

    copied = out / "hub" / builder.repo_dir_name(REPO) / "snapshots" / revision / "model.safetensors"
    assert not copied.is_symlink()
    assert copied.read_bytes() == WEIGHT
