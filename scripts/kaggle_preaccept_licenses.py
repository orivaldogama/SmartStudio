#!/usr/bin/env python3
"""Record Max-pack licence acceptance for an ephemeral Kaggle session (T8 / gap 2).

The session's data root (``OMNIVOICE_DATA_DIR``, ``/kaggle/working/omnivoice``
on Kaggle) dies with the session, so every fresh boot would ask again for the
gated models in the Max pack — OmniVoice's non-commercial weights and NLLB-200
(CC-BY-NC). The bootstrap notebook runs this script as the session's
**explicit acceptance input**: it records through the backend's own
``services.model_acceptance.accept()`` with the live terms fingerprint — the
same gate and binding the app UI uses, never a hand-written record — so a
later terms change still asks again.

The script refuses to run without ``OMNIVOICE_DATA_DIR`` set, so it can never
write into a developer's real profile by accident.

    OMNIVOICE_DATA_DIR=/kaggle/working/omnivoice \
        python scripts/kaggle_preaccept_licenses.py
    python scripts/kaggle_preaccept_licenses.py --check    # report only, write nothing
    python scripts/kaggle_preaccept_licenses.py --repo-id facebook/nllb-200-distilled-600M

Exit 0 when every model ended accepted or not gated; 1 while anything remains
gated; 2 when ``OMNIVOICE_DATA_DIR`` is missing.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_ROOT = _SCRIPTS.parent


def default_repos() -> tuple[str, ...]:
    """The Max pack — the single source of truth shared with the dataset builder."""
    if str(_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS))
    from build_kaggle_dataset import MAX_PACK_REPOS  # noqa: PLC0415

    return MAX_PACK_REPOS


def record(acceptance, repos: Iterable[str], *, check: bool = False) -> list[str]:
    """Report (and unless ``check``, record) each repo through the real gate.

    ``acceptance`` is ``services.model_acceptance`` (or a stand-in with the same
    ``status``/``accept`` surface). Returns the repo ids that remain gated.
    """
    gated: list[str] = []
    for repo_id in dict.fromkeys(r for r in repos if r):
        state = acceptance.status(repo_id)
        if not state["required"]:
            print(f"{repo_id}: not gated ({state['category']})")
            continue
        if state["state"] == "accepted":
            print(f"{repo_id}: already accepted ({state['license']})")
            continue
        if check:
            print(f"{repo_id}: GATED ({state['license']}, state {state['state']})")
            gated.append(repo_id)
            continue
        try:
            # Bind the acceptance to exactly the terms just read — the same
            # contract the UI dialog has: changed terms raise instead of
            # silently accepting whatever is current now.
            acceptance.accept(repo_id, state["fingerprint"])
        except ValueError:
            print(f"{repo_id}: terms changed while recording; re-run", file=sys.stderr)
            gated.append(repo_id)
            continue
        print(f"{repo_id}: accepted {state['license']} ({state['category']})")
    return gated


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record Max-pack licence acceptance for an ephemeral session.",
    )
    parser.add_argument(
        "--repo-id", action="append", dest="repo_ids",
        help="record a specific model instead of the whole Max pack (repeatable)",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="report acceptance only; write nothing",
    )
    args = parser.parse_args(argv)

    data_dir = (os.environ.get("OMNIVOICE_DATA_DIR") or "").strip()
    if not data_dir:
        print(
            "refusing to run: set OMNIVOICE_DATA_DIR to the session's ephemeral data "
            "root (on Kaggle: /kaggle/working/omnivoice) — this script must never "
            "write into a real user profile by accident.",
            file=sys.stderr,
        )
        return 2

    repos = tuple(args.repo_ids) if args.repo_ids else default_repos()

    backend = _ROOT / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from core.db import init_db  # noqa: PLC0415
    from services import model_acceptance  # noqa: PLC0415

    # Idempotent, and the backend's own startup runs it again: creates the
    # settings table inside OMNIVOICE_DATA_DIR before anything writes to it.
    init_db()

    gated = record(model_acceptance, repos, check=args.check)
    if gated:
        print("still gated: " + ", ".join(gated), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
