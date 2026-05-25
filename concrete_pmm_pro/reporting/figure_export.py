"""Low-level figure export helpers for future report generation."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from typing import Any


def plotly_figure_to_html_bytes(fig: Any) -> bytes:
    """Return standalone Plotly HTML bytes for an existing figure."""

    return fig.to_html(full_html=True, include_plotlyjs="cdn").encode("utf-8")


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            text=True,
        )
    else:
        process.kill()


def plotly_figure_to_png_bytes(fig: Any, timeout_seconds: float = 20.0) -> tuple[bytes | None, list[str]]:
    """Return PNG bytes when static image export is available.

    Plotly PNG export requires kaleido. The app should continue to work when
    kaleido is absent or hangs during engine startup, so failures are returned
    as warnings instead of raised.
    """

    export_script = (
        "import base64, json, sys\n"
        "import plotly.io as pio\n"
        "try:\n"
        "    if hasattr(pio, 'kaleido') and getattr(pio.kaleido, 'scope', None) is not None:\n"
        "        pio.kaleido.scope.mathjax = None\n"
        "    fig = pio.from_json(sys.stdin.read())\n"
        "    data = fig.to_image(format='png')\n"
        "    print(json.dumps({'png': base64.b64encode(data).decode('ascii'), 'warning': None}))\n"
        "except Exception as exc:\n"
        "    print(json.dumps({'png': None, 'warning': str(exc)}))\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", export_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(fig.to_json(), timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        return None, [f"PNG export requires kaleido. HTML export remains available. Detail: export timed out after {timeout_seconds:g} seconds."]
    except Exception as exc:
        return None, [f"PNG export requires kaleido. HTML export remains available. Detail: {exc}"]
    if process.returncode:
        detail = (stderr or stdout or "static image export process failed").strip()
        return None, [f"PNG export requires kaleido. HTML export remains available. Detail: {detail}"]
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        detail = (stdout or stderr or str(exc)).strip()
        return None, [f"PNG export requires kaleido. HTML export remains available. Detail: {detail}"]
    if payload.get("png"):
        return base64.b64decode(payload["png"]), []
    return None, [f"PNG export requires kaleido. HTML export remains available. Detail: {payload.get('warning') or 'PNG export returned no image data.'}"]
