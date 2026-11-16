"""Tests for scripts/kaggle_preaccept_licenses.py (T8) and its notebook wiring.

The script keeps its backend imports lazy, so the guard, the shared Max-pack
list and the recording flow (through a stand-in with the real
``model_acceptance`` surface) all run on plain pytest without the dependency
stack. The notebook contract keeps the acceptance cell ahead of the backend
start, so nothing writes the settings DB concurrently.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    # Loaded by path, not as `scripts.<name>`: pytest imports this very file as
    # scripts.test_* (tests/scripts/ has an __init__.py), so the `scripts` name
    # is already taken by the test package. Same pattern as test_update_contributors.
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = _load("build_kaggle_dataset", ROOT / "scripts" / "build_kaggle_dataset.py")
preaccept = _load(
    "kaggle_preaccept_licenses", ROOT / "scripts" / "kaggle_preaccept_licenses.py"
)

NOTEBOOK = ROOT / "notebooks" / "VoiceStudio_Kaggle_2xT4.ipynb"
SCRIPT = ROOT / "scripts" / "kaggle_preaccept_licenses.py"


class FakeAcceptance:
    """The model_acceptance surface the script uses, with canned states."""

    def __init__(self, states: dict[str, dict]):
        self.states = states
        self.accepted: list[tuple[str, str]] = []
        self.raise_on_accept: set[str] = set()

    def status(self, repo_id):
        return self.states[repo_id]

    def accept(self, repo_id, fingerprint):
        if repo_id in self.raise_on_accept:
            raise ValueError("terms_changed")
        self.accepted.append((repo_id, fingerprint))
        return {"state": "accepted"}


def _state(repo, *, required=True, state="not_accepted", license_="CC-BY-NC", fingerprint="v2:x"):
    return {
        "repo_id": repo,
        "required": required,
        "state": state,
        "license": license_,
        "category": "non-commercial" if required else "commercial",
        "fingerprint": fingerprint,
    }


def test_defaults_to_the_builders_max_pack():
    assert preaccept.default_repos() == builder.MAX_PACK_REPOS


def test_refuses_without_an_explicit_data_dir(monkeypatch):
    monkeypatch.delenv("OMNIVOICE_DATA_DIR", raising=False)
    assert preaccept.main([]) == 2


def test_records_through_the_real_gate_with_the_live_fingerprint():
    fake = FakeAcceptance({
        "a/gated": _state("a/gated", fingerprint="v2:aaa"),
        "b/open": _state("b/open", required=False),
        "c/done": _state("c/done", state="accepted"),
    })
    # A repeated id is recorded once; open and already-accepted models are left alone.
    assert preaccept.record(fake, ["a/gated", "b/open", "c/done", "a/gated"]) == []
    assert fake.accepted == [("a/gated", "v2:aaa")]


def test_check_mode_writes_nothing_and_reports_gated():
    fake = FakeAcceptance({"a/gated": _state("a/gated")})
    assert preaccept.record(fake, ["a/gated"], check=True) == ["a/gated"]
    assert fake.accepted == []


def test_a_terms_change_while_recording_fails_closed():
    fake = FakeAcceptance({"a/gated": _state("a/gated")})
    fake.raise_on_accept.add("a/gated")
    assert preaccept.record(fake, ["a/gated"]) == ["a/gated"]


def _cell_sources() -> list[str]:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(cell["source"]) for cell in notebook["cells"]]


def test_notebook_runs_the_script_before_the_backend_starts():
    sources = _cell_sources()
    accept = next(i for i, s in enumerate(sources) if "kaggle_preaccept_licenses.py" in s)
    start = next(i for i, s in enumerate(sources) if "session_control:app" in s)
    assert accept < start, "acceptance must run before uvicorn opens the settings DB"
    assert 'os.environ["OMNIVOICE_DATA_DIR"] = str(DATA_DIR)' in sources[accept]


def test_the_run_is_framed_as_an_explicit_user_act():
    sources = _cell_sources()
    accept = next(i for i, s in enumerate(sources) if "kaggle_preaccept_licenses.py" in s)
    framing = next(i for i, s in enumerate(sources) if "Accept the model licences" in s)
    assert framing < accept
    # Whitespace-normalized: markdown wraps phrases across lines.
    lowered = " ".join(sources[framing].split()).lower()
    assert "explicit acceptance" in lowered
    assert "non-commercial" in lowered


def test_the_script_never_hand_writes_the_acceptance_store():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "model_acceptance" in source and ".accept(" in source
    assert "model_licence_accepted:" not in source
    assert "settings_store" not in source
