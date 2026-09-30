"""Describe a managed server as a Vela surface (surface v1).

Pure functions only: the blueprint asks the agent, this module turns the
answers into the JSON the frontend draws. Keeping it free of Flask and the
panel means the same document can be served to anything that speaks the
format — the panel's own renderer today, a Vela app tomorrow.

Contract: https://github.com/jhd3197/vela-contracts/blob/main/docs/SURFACES.md
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

SURFACE_VERSION = 1
REFRESH_SECONDS = 4

#: Actions this surface can offer. The blueprint maps each to one agent
#: command and validates the input again before sending it; nothing here is
#: trusted just because a button carried it.
ACTIONS = {
    "restart-container": {
        "id": "restart-container",
        "title": "Restart container",
        "confirm": "Restart this container? It will be briefly unavailable.",
        "danger": True,
    },
    "restart-service": {
        "id": "restart-service",
        "title": "Restart service",
        "confirm": "Restart this service? It will be briefly unavailable.",
        "danger": True,
    },
}

#: Container ids are hex; names are Docker's own charset.
CONTAINER_REF = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")
#: systemd unit names, restricted to services.
SERVICE_UNIT = re.compile(r"^[a-zA-Z0-9:_.@-]{1,200}\.service$")

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _slug(value: Any, fallback: str) -> str:
    slug = _SLUG_STRIP.sub("-", str(value or "").lower()).strip("-")[:64]
    return slug or fallback


def _text(value: Any, limit: int) -> str:
    return str(value if value is not None else "")[:limit]


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _pct(value: Any) -> float:
    number = _num(value)
    return 0.0 if number is None else round(max(0.0, min(number, 100.0)), 1)


def _usage_tone(percent: float) -> str:
    if percent >= 90:
        return "bad"
    if percent >= 75:
        return "warn"
    return "neutral"


def _os_label(info: dict) -> str:
    """`platform platform_version` (Ubuntu 24.04), falling back to `os`."""
    platform = (info.get("platform") or "").strip()
    version = (info.get("platform_version") or "").strip()
    label = f"{platform.capitalize()} {version}".strip() if platform else ""
    return label or (info.get("os") or "").strip() or "Unknown"


def _processes(processes: list) -> list[dict]:
    """The busiest processes. The agent returns every process unsorted and
    ignores a limit, so the ranking happens here."""
    rows = [p for p in processes if isinstance(p, dict)]
    rows.sort(key=lambda p: (_num(p.get("cpu_percent")) or 0.0, _num(p.get("mem_percent")) or 0.0), reverse=True)
    return rows


def _containers_window(containers: list, can_act: bool) -> dict | None:
    rows = [c for c in containers if isinstance(c, dict)]
    if not rows:
        return None
    rows.sort(key=lambda c: (c.get("state") != "running", str(c.get("name") or "")))
    children: list[dict] = [{
        "type": "table",
        "columns": [
            {"key": "name", "label": "Container"},
            {"key": "image", "label": "Image"},
            {"key": "status", "label": "Status"},
        ],
        "rows": [
            {
                "name": _text(c.get("name") or c.get("id", "")[:12], 500),
                "image": _text(c.get("image"), 500),
                "status": _text(c.get("status") or c.get("state"), 500),
            }
            for c in rows[:50]
        ],
    }]
    if can_act:
        buttons = [
            {
                "type": "button",
                "label": _text(f"Restart {c.get('name') or c.get('id', '')[:12]}", 40),
                "action": "restart-container",
                "input": {"container": _text(c.get("id"), 200)},
                "icon": "rotate-cw",
            }
            for c in rows[:6]
            if c.get("state") == "running" and CONTAINER_REF.match(str(c.get("id") or ""))
        ]
        if buttons:
            children.append({"type": "stack", "direction": "row", "gap": "s", "children": buttons})
    running = sum(1 for c in rows if c.get("state") == "running")
    return {
        "type": "window", "id": "containers", "title": f"Containers ({running}/{len(rows)})",
        "icon": "container", "size": "wide",
        "tone": "warn" if running < len(rows) else "neutral",
        "children": children,
    }


def _services_window(units: list, can_act: bool) -> dict | None:
    rows = [u for u in units if isinstance(u, dict) and u.get("unit")]
    if not rows:
        return None
    failed = [u for u in rows if u.get("active") == "failed"]
    running = [u for u in rows if u.get("sub") == "running"]
    shown = (failed + [u for u in running if u not in failed])[:40]
    children: list[dict] = [{
        "type": "list",
        "rows": [
            {
                "label": _text(u.get("unit"), 200),
                "detail": _text(u.get("description") or u.get("sub"), 200),
                "badge": _text(u.get("sub") or u.get("active"), 20),
                "tone": "bad" if u.get("active") == "failed" else "good",
            }
            for u in shown
        ],
    }]
    if can_act:
        buttons = [
            {
                "type": "button",
                "label": _text(f"Restart {u['unit'].removesuffix('.service')}", 40),
                "action": "restart-service",
                "input": {"unit": u["unit"]},
                "tone": "warn",
                "icon": "rotate-cw",
            }
            for u in failed[:6]
            if SERVICE_UNIT.match(u["unit"])
        ]
        if buttons:
            children.append({"type": "stack", "direction": "row", "gap": "s", "children": buttons})
    return {
        "type": "window", "id": "services",
        "title": f"Services ({len(running)} running{f', {len(failed)} failed' if failed else ''})",
        "icon": "boxes", "size": "tall",
        "tone": "bad" if failed else "neutral",
        "children": children,
    }


def build_server_surface(
    *,
    server_name: str,
    info: dict | None = None,
    metrics: dict | None = None,
    processes: list | None = None,
    containers: list | None = None,
    units: list | None = None,
    cpu_history: list | None = None,
    can_act: bool = False,
    offline: bool = False,
    now: datetime | None = None,
) -> dict:
    """One server as a surface-v1 desktop.

    Every input is optional: a section whose data did not arrive is left out
    rather than drawn empty, so an agent without Docker or systemd still gets
    a tidy desktop.
    """
    now = now or datetime.now(timezone.utc)
    info = info if isinstance(info, dict) else {}
    metrics = metrics if isinstance(metrics, dict) else {}
    hostname = _text(info.get("hostname") or server_name or "server", 80) or "server"

    document: dict[str, Any] = {
        "surface": SURFACE_VERSION,
        "id": _slug(hostname, "server"),
        "title": hostname,
        "icon": "server",
        "lang": "en",
        "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expiresAt": (now + timedelta(seconds=REFRESH_SECONDS * 15)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "refresh": {"every": REFRESH_SECONDS},
    }

    if offline:
        document["subtitle"] = "Agent offline"
        document["root"] = {"type": "empty", "icon": "plug-zap", "message": "This server's agent is offline. The desktop will come back when it reconnects."}
        return document

    arch = info.get("architecture")
    document["subtitle"] = _text(" · ".join(x for x in (_os_label(info), arch) if x), 200)

    windows: list[dict] = []

    # System: static facts plus the live numbers that matter.
    system_children: list[dict] = [{
        "type": "keyvalue",
        "rows": [
            row for row in (
                {"label": "OS", "value": _text(_os_label(info), 200)},
                {"label": "Kernel", "value": _text(info.get("kernel_version"), 200)} if info.get("kernel_version") else None,
                {"label": "CPU", "value": _text(info.get("cpu_model"), 200)} if info.get("cpu_model") else None,
                {"label": "Cores", "value": info["cpu_cores"], "format": "number"} if _num(info.get("cpu_cores")) is not None else None,
                {"label": "Memory", "value": info["total_memory"], "format": "bytes"} if _num(info.get("total_memory")) else None,
                {"label": "Uptime", "value": metrics["uptime"], "format": "duration"} if _num(metrics.get("uptime")) else None,
            ) if row
        ],
    }]
    if metrics:
        cpu = _pct(metrics.get("cpu_percent"))
        mem = _pct(metrics.get("memory_percent"))
        system_children.append({"type": "grid", "columns": 2, "children": [
            {"type": "stat", "label": "CPU", "value": cpu, "format": "percent", "tone": _usage_tone(cpu)},
            {"type": "stat", "label": "Memory", "value": mem, "format": "percent", "tone": _usage_tone(mem)},
        ]})
    history = [float(v) for v in (cpu_history or []) if _num(v) is not None][-60:]
    if len(history) >= 2:
        system_children.append({"type": "chart", "kind": "line", "label": "CPU, recent", "series": history, "domain": [0, 100]})
    windows.append({"type": "window", "id": "system", "title": "System", "icon": "monitor", "children": system_children})

    services = _services_window(units or [], can_act)
    if services:
        windows.append(services)
    docker = _containers_window(containers or [], can_act)
    if docker:
        windows.append(docker)

    ranked = _processes(processes or [])
    if ranked:
        windows.append({
            "type": "window", "id": "processes", "title": "Top processes", "icon": "activity",
            "children": [{
                "type": "table",
                "columns": [
                    {"key": "name", "label": "Process"},
                    {"key": "cpu", "label": "CPU", "align": "end", "format": "percent"},
                    {"key": "mem", "label": "Memory", "align": "end", "format": "percent"},
                ],
                "rows": [
                    {"name": _text(p.get("name") or p.get("pid"), 500), "cpu": _pct(p.get("cpu_percent")), "mem": _pct(p.get("mem_percent"))}
                    for p in ranked[:10]
                ],
            }],
        })

    # The agent reports one aggregate disk figure, not per-mount usage.
    if _num(metrics.get("disk_total")):
        disk = _pct(metrics.get("disk_percent"))
        windows.append({
            "type": "window", "id": "storage", "title": "Storage", "icon": "hard-drive", "size": "s",
            "children": [{
                "type": "progress", "label": "Disk", "value": disk, "tone": _usage_tone(disk),
                "caption": _text(f"{_bytes(metrics.get('disk_used'))} of {_bytes(metrics.get('disk_total'))} used", 200),
            }],
        })

    dock = [
        {"id": w["id"], "label": _text(w["title"].split(" (")[0], 60), "icon": w["icon"], "window": w["id"], **({"tone": w["tone"]} if w.get("tone") not in (None, "neutral") else {})}
        for w in windows
    ]

    actions = sorted({
        button["action"]
        for w in windows for child in w["children"] if child["type"] == "stack"
        for button in child["children"] if button["type"] == "button"
    })
    if actions:
        document["actions"] = [ACTIONS[a] for a in actions]

    document["root"] = {"type": "desktop", "title": hostname, "wallpaper": "dusk", "windows": windows, "dock": dock}
    return document


def _bytes(value: Any) -> str:
    """Only for captions, which are plain text; values elsewhere stay raw so
    the host formats them for the viewer's locale."""
    number = _num(value) or 0.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.0f} {unit}" if unit == "B" else f"{number:.1f} {unit}"
        number /= 1024
    return f"{number:.1f} TB"
