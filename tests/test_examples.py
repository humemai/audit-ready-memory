"""The documented examples run and print what the documentation says they show."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _run(name: str) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / name)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_removal_request():
    out = _run("removal_request.py")
    assert "recalled before the removal: [0, 1]" in out
    assert "recalled after the removal: [1]" in out
    assert "removed by event 3: the resident asked to remove the phone number" in out
    assert "read by events: [2]" in out
    assert "original still in the log: True" in out


def test_look_back():
    out = _run("look_back.py")
    assert "shown then: ['the repair is planned for Monday']" in out
    assert "expiry recorded as event 3: 1 item" in out
    assert "in memory at the first recall: 2 items" in out
    assert (
        "in memory now: ['the repair is planned for Monday', "
        "'the repair moves to Tuesday']" in out
    )
    assert "recall counts: [1]" in out


def test_export_holds_no_content():
    out = _run("export_audit_log.py")
    lines = out.strip().splitlines()
    assert lines[0] == "seq,timestamp,kind,session,who,items,reason"
    assert len(lines) == 4
    assert "private detail" not in out
    assert lines[3].endswith(",deletion,,a,0,asked to remove")


def test_verify_script_parses():
    subprocess.run(["bash", "-n", str(ROOT / "scripts" / "verify.sh")], check=True)
