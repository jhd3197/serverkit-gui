"""ServerKit Agent GUI plugin — panel-side blueprint.

Proxies the agent's gui:* actions for the live screen, and describes the
server as a surface-v1 document for hosts without one. No frame data is stored; everything is forwarded through plugins_sdk.agents,
which checks this plugin declared ``agent.command:<action>`` before dispatching
and turns a failed command into an exception carrying the reason.
"""
from collections import deque

from flask import Blueprint, jsonify, request

from app.middleware.rbac import auth_required, developer_required, get_current_user
from app.middleware.api_scope_middleware import require_scope
from app.plugins_sdk import agents, logger
from app.plugins_sdk.permissions import PermissionDenied
from app.models.server import Server

from .surface import ACTIONS, CONTAINER_REF, SERVICE_UNIT, build_server_surface

gui_bp = Blueprint("server_gui", __name__)
log = logger(__name__)

PLUGIN_SLUG = "serverkit-gui"

DEFAULT_FRAME_TIMEOUT = 8.0
MAX_FRAME_TIMEOUT = 15.0


def _fleet():
    return agents.for_plugin(PLUGIN_SLUG)


def _server_or_404(server_id: str):
    server = Server.query.get(server_id)
    if not server:
        return None, (jsonify({"error": "Server not found"}), 404)
    return server, None


@gui_bp.route("/<server_id>/capabilities", methods=["GET"])
@auth_required()
@require_scope("servers:read")
def capabilities(server_id):
    """Ask the agent what it can capture (display server, resolution, fps cap).

    API-key capable on purpose: a Vela host polls this with a scoped key."""
    user = get_current_user()
    server, err = _server_or_404(server_id)
    if err:
        return err

    if server.status != "online":
        return jsonify({
            "capability": "none",
            "reason": "agent_offline",
            "synthetic_fallback": True,
        })

    try:
        data = _fleet().run(
            server_id, "gui:capabilities",
            timeout=5.0,
            user_id=user.id if user else None,
        )
    except (agents.CommandError, PermissionDenied) as exc:
        # Not an error state: an agent that doesn't implement gui:capabilities
        # is exactly what the synthetic fallback exists for.
        return jsonify({
            "capability": "none",
            "reason": str(exc),
            "synthetic_fallback": True,
        })

    if not isinstance(data, dict):
        data = {}
    data.setdefault("synthetic_fallback", data.get("capability") in (None, "none"))
    return jsonify(data)


@gui_bp.route("/<server_id>/frame", methods=["GET"])
@auth_required()
@require_scope("servers:read")
def frame(server_id):
    """Capture and return a single frame. API-key capable (see capabilities).

    Query params:
      scale   float 0.1..1.0   server-side downscale before encoding
      quality int   10..95     JPEG quality (PNG ignores this)
      format  png|jpeg         encoding hint
    """
    user = get_current_user()
    server, err = _server_or_404(server_id)
    if err:
        return err

    if server.status != "online":
        return jsonify({"error": "agent offline", "code": "AGENT_OFFLINE"}), 503

    try:
        scale = float(request.args.get("scale", "0.75"))
        quality = int(request.args.get("quality", "70"))
    except ValueError:
        return jsonify({"error": "scale/quality must be numeric"}), 400

    scale = max(0.1, min(scale, 1.0))
    quality = max(10, min(quality, 95))
    fmt = request.args.get("format", "jpeg").lower()
    if fmt not in ("jpeg", "png"):
        fmt = "jpeg"

    try:
        data = _fleet().run(
            server_id, "gui:screenshot",
            {"scale": scale, "quality": quality, "format": fmt},
            timeout=DEFAULT_FRAME_TIMEOUT,
            user_id=user.id if user else None,
        )
    except PermissionDenied as exc:
        # Only reachable if this plugin's manifest lost the permission.
        return jsonify({"error": str(exc), "code": "PERMISSION_DENIED"}), 403
    except agents.CommandError as exc:
        return jsonify({"error": str(exc), "code": exc.code or "CAPTURE_FAILED"}), 502

    # Expected agent shape:
    #   { "image_base64": "...", "format": "jpeg", "width": 1920, "height": 1080,
    #     "captured_at": "2026-05-01T12:34:56Z" }
    if not isinstance(data, dict) or "image_base64" not in data:
        return jsonify({"error": "agent returned no frame"}), 502

    return jsonify(data)


def _best_effort(server_id, user_id, action, params, default):
    """Ask the agent, but never fail the page over the answer.

    The surface renders *something* for any host, so an agent that won't
    answer (no Docker, no systemd, older build) leaves its section out rather
    than erroring. A permission this plugin hasn't been granted lands in the
    same place deliberately: an install whose stored manifest predates these
    actions keeps working instead of 500-ing, and the log line says why.
    """
    try:
        return _fleet().run(server_id, action, params, timeout=5.0,
                            user_id=user_id)
    except PermissionDenied as exc:
        log.warning('%s: %s — update the extension to restore full '
                    'desktop detail', PLUGIN_SLUG, exc)
        return default
    except agents.CommandError:
        return default


#: Recent CPU readings per server, for the System window's chart. In-process
#: and best effort: a restart or a second worker just starts a new line.
_cpu_history: dict[str, deque] = {}


@gui_bp.route("/<server_id>/surface", methods=["GET"])
@auth_required()
@require_scope("servers:read")
def server_surface(server_id):
    """The server as a surface-v1 document (see backend/surface.py).

    No new agent action: this reuses what the agent already exposes. It is
    what the panel draws for a host without a display, and a format any other
    host (Vela) can draw too.
    """
    user = get_current_user()
    server, err = _server_or_404(server_id)
    if err:
        return err

    if server.status != "online":
        return jsonify(build_server_surface(server_name=server.name, offline=True))

    user_id = user.id if user else None
    ask = lambda action, params, default: _best_effort(server_id, user_id, action, params, default)  # noqa: E731

    metrics = ask("system:metrics", {}, {})
    if isinstance(metrics, dict) and isinstance(metrics.get("cpu_percent"), (int, float)):
        _cpu_history.setdefault(server_id, deque(maxlen=60)).append(metrics["cpu_percent"])
    units = ask("systemd:list_units", {"type": "service"}, {})

    return jsonify(build_server_surface(
        server_name=server.name,
        info=ask("system:info", {}, {}),
        metrics=metrics,
        processes=ask("system:processes", {}, []),
        containers=ask("docker:container:list", {"all": True}, []),
        units=units.get("units") if isinstance(units, dict) else [],
        cpu_history=list(_cpu_history.get(server_id, ())),
        can_act=bool(user and user.is_active and user.is_developer),
    ))


@gui_bp.route("/<server_id>/actions/<action_id>", methods=["POST"])
@developer_required
def run_action(server_id, action_id):
    """Run one of the surface's declared actions.

    The surface only says which action and on what; the input is validated
    again here and mapped to exactly one agent command. Developer role, same
    as the panel's own container routes.
    """
    user = get_current_user()
    server, err = _server_or_404(server_id)
    if err:
        return err
    if action_id not in ACTIONS:
        return jsonify({"error": "Unknown action", "code": "UNKNOWN_ACTION"}), 404
    if server.status != "online":
        return jsonify({"error": "agent offline", "code": "AGENT_OFFLINE"}), 503

    body = request.get_json(silent=True) or {}
    params = body.get("input") if isinstance(body.get("input"), dict) else {}

    if action_id == "restart-container":
        ref = params.get("container")
        if not isinstance(ref, str) or not CONTAINER_REF.match(ref):
            return jsonify({"error": "container is required", "code": "INVALID_INPUT"}), 400
        command, command_params = "docker:container:restart", {"id": ref}
    else:  # restart-service
        unit = params.get("unit")
        if not isinstance(unit, str) or not SERVICE_UNIT.match(unit):
            return jsonify({"error": "unit must be a .service unit", "code": "INVALID_INPUT"}), 400
        command, command_params = "systemd:restart", {"unit": unit}

    log.info('%s: %s on %s by user %s (%s)', PLUGIN_SLUG, action_id, server_id,
             user.id if user else None, command_params)
    try:
        _fleet().run(server_id, command, command_params, timeout=30.0,
                     user_id=user.id if user else None)
    except PermissionDenied as exc:
        return jsonify({"error": str(exc), "code": "PERMISSION_DENIED"}), 403
    except agents.CommandError as exc:
        return jsonify({"error": str(exc), "code": exc.code or "ACTION_FAILED"}), 502
    return jsonify({"ok": True})
