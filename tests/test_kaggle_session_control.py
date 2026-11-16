"""The Kaggle notebook must ship the session-shutdown control the desktop app calls.

Settings -> Sharing -> Remote backend -> "Shut down session" POSTs
``/api/session-control/shutdown`` at the tunnel URL; the notebook's sidecar
module serves that route, stops the tunnel, ends the kernel (which ends the
Kaggle session and its GPU quota) and exits uvicorn. These checks parse the
committed notebook so a cell edit cannot silently drop the contract.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_NOTEBOOK = _ROOT / "notebooks" / "VoiceStudio_Kaggle_2xT4.ipynb"


def _cell_sources() -> list[str]:
    notebook = json.loads(_NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(cell["source"]) for cell in notebook["cells"]]


def _control_cell() -> str:
    for source in _cell_sources():
        if "SESSION_CONTROL_SOURCE" in source:
            return source
    pytest.fail("no notebook cell defines SESSION_CONTROL_SOURCE")


def _module_source() -> str:
    match = re.search(r'SESSION_CONTROL_SOURCE = """(.*?)"""', _control_cell(), re.DOTALL)
    assert match, "SESSION_CONTROL_SOURCE must be a triple-quoted template"
    return (
        match.group(1)
        .replace("__BACKEND_DIR__", "/opt/backend")
        .replace("__TUNNEL_PID__", "/tmp/tunnel.pid")
    )


def test_the_control_module_is_valid_python():
    compile(_module_source(), "session_control.py", "exec")


def test_shutdown_route_is_posted_first_and_rejects_anonymous_callers():
    module = _module_source()
    assert '"/api/session-control/shutdown"' in module
    assert 'methods=["POST"]' in module
    # Position 0 keeps the SPA catch-all mount from swallowing the path.
    assert re.search(r"routes\.insert\(\s*\n?\s*0", module), (
        "the route must be inserted ahead of every other route"
    )
    assert 'startswith("bearer ")' in module
    assert "status_code=401" in module
    assert "status_code=202" in module


def test_shutdown_stops_tunnel_then_kernel_then_self():
    module = _module_source()
    # The tunnel pid is only signalled while /proc still proves it is cloudflared.
    assert '"/proc/%d/cmdline"' in module
    assert '"cloudflared"' in module
    # The kernel (this process's parent) gets SIGTERM, then SIGKILL on a deadline.
    assert "os.getppid()" in module
    assert "signal.SIGTERM" in module
    assert "signal.SIGKILL" in module
    # And the server itself exits last, so nothing keeps the VM busy.
    assert "os._exit(0)" in module
    assert module.index("_terminate_from_pidfile(TUNNEL_PID") < module.index("os.getppid()")


def test_server_starts_through_the_control_module():
    cell = _control_cell()
    assert '"session_control:app"' in cell, "uvicorn must serve the sidecar, not main:app"
    assert '"--app-dir", str(WORK)' in cell
    assert "CONTROL.write_text(" in cell
    assert '.replace("__BACKEND_DIR__", str(SRC / "backend"))' in cell
    assert '.replace("__TUNNEL_PID__", str(TUNNEL_PID))' in cell
    # Server mode and the API key stay on: the Bearer gate authenticates the
    # shutdown call exactly like every other remote request.
    assert '"OMNIVOICE_SERVER_MODE": "1"' in cell
    assert '"OMNIVOICE_API_KEY": API_KEY' in cell


def test_tunnel_cell_records_its_pid_for_the_control_module():
    # Select on the Popen assignment, not bare keywords: the start cell now
    # also mentions "cloudflared" (inside the sidecar template).
    tunnel = next(
        source for source in _cell_sources() if "tunnel = subprocess.Popen" in source
    )
    assert '(WORK / "tunnel.pid").write_text(str(tunnel.pid))' in tunnel


def test_manual_cleanup_removes_the_pid_file():
    cleanup = next(
        source
        for source in _cell_sources()
        if "stopped" in source and "tunnel.pid" in source
    )
    assert "unlink()" in cleanup
