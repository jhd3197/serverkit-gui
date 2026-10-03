"""Blueprint auth: the read routes accept a JWT *or* a scoped API key.

The capabilities, frame and surface routes were converted from bare
``@jwt_required()`` to ``auth_required()`` + ``require_scope("servers:read")``
so a Vela host can poll them with one scoped ServerKit key (``X-API-Key``).
JWT callers are unaffected, a key without the scope gets 403 and no
credentials get 401.

These tests run against the real ServerKit app from the sibling checkout
(``SERVERKIT_BACKEND`` env overrides the default ``../ServerKit/backend``)
and skip cleanly when it isn't available — the same pattern the panel's own
extension suites use for extracted plugins.

Run with: python -m unittest discover -s tests
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("SERVERKIT_BACKEND")
               or (ROOT.parent / "ServerKit" / "backend"))

if not (BACKEND / "app" / "__init__.py").is_file():
    raise unittest.SkipTest(
        f"ServerKit backend not found at {BACKEND} (set SERVERKIT_BACKEND)")

# Test-environment knobs must be set before the ServerKit app package imports.
os.environ.setdefault("FLASK_ENV", "testing")
os.environ.setdefault("SERVERKIT_REGISTRY_URL", "")
_DB_FILE = os.path.join(
    tempfile.gettempdir(), f"serverkit_gui_test_{os.getpid()}.db").replace("\\", "/")
os.environ["TEST_DATABASE_URL"] = "sqlite:///" + _DB_FILE

sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)  # instance/config paths resolve relative to the backend

from app import create_app, db  # noqa: E402
from app.models import User  # noqa: E402
from app.models.plugin import InstalledPlugin  # noqa: E402
from app.models.server import Server  # noqa: E402
from app.services.agent_registry import agent_registry  # noqa: E402
from app.services.api_key_service import ApiKeyService  # noqa: E402
from flask_jwt_extended import create_access_token  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

# Agent payloads the panel would unwrap from a real gui-capable agent.
AGENT_PAYLOADS = {
    "gui:capabilities": {"capability": "screenshot", "fps_cap": 5},
    "gui:screenshot": {"image_base64": "aGk=", "format": "jpeg",
                       "width": 8, "height": 8},
    "system:info": {"hostname": "box"},
    "system:metrics": {"cpu_percent": 5.0, "memory_percent": 10.0},
    "system:processes": [],
    "docker:container:list": [],
    "systemd:list_units": {"units": []},
}


def _dispatch(server_id, action, params=None, timeout=45.0, user_id=None):
    return {"success": True, "data": AGENT_PAYLOADS.get(action, {})}


class BlueprintAuthTests(unittest.TestCase):
    """One online server, one user; the agent fleet is stubbed at the seams
    the plugins_sdk already patches around (registry + dispatcher)."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app("testing")
        with cls.app.app_context():
            db.create_all()
        # Load this repo's backend as the installed plugin package and mount
        # its blueprint at the manifest's prefix, mirroring a real install.
        pkg = "app.plugins.serverkit-gui"
        if pkg not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                pkg, ROOT / "backend" / "__init__.py",
                submodule_search_locations=[str(ROOT / "backend")])
            module = importlib.util.module_from_spec(spec)
            sys.modules[pkg] = module
            spec.loader.exec_module(module)
        gui_bp = sys.modules[pkg].gui_bp
        if gui_bp.name not in cls.app.blueprints:
            cls.app.register_blueprint(gui_bp, url_prefix="/api/v1/server-gui")
        cls.client = cls.app.test_client()
        cls.manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.drop_all()
        db.create_all()
        plugin = InstalledPlugin(
            name="serverkit-gui",
            display_name=self.manifest.get("display_name", "serverkit-gui"),
            slug="serverkit-gui", version=self.manifest.get("version", "0.0.0"),
            status=InstalledPlugin.STATUS_ACTIVE, has_backend=True,
            url_prefix="/api/v1/server-gui", manifest=self.manifest)
        db.session.add(plugin)
        self.server = Server(name="box", hostname="10.0.0.1", status="online")
        db.session.add(self.server)
        self.user = User(email="vela-poll@t.local", username="vela_poll",
                         password_hash=generate_password_hash("x"),
                         role="developer", is_active=True)
        db.session.add(self.user)
        db.session.commit()
        self.server_id = self.server.id
        for patcher in (
            mock.patch.object(agent_registry, "is_agent_connected",
                              return_value=True),
            mock.patch("app.services.remote_command_dispatcher"
                       ".dispatch_agent_command", side_effect=_dispatch),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.ctx.pop)

    def _api_key_headers(self, scopes):
        _, raw_key = ApiKeyService.create_key(
            self.user.id, name="vela-poll", scopes=scopes)
        return {"X-API-Key": raw_key}

    def _jwt_headers(self):
        return {"Authorization": f"Bearer {create_access_token(identity=self.user.id)}"}

    def _url(self, suffix):
        return f"/api/v1/server-gui/{self.server_id}/{suffix}"

    # (a) a key with servers:read reaches each converted route
    def test_scoped_api_key_gets_200_on_all_three_routes(self):
        headers = self._api_key_headers(["servers:read"])
        resp = self.client.get(self._url("capabilities"), headers=headers)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertEqual(resp.get_json()["capability"], "screenshot")

        resp = self.client.get(self._url("frame"), headers=headers)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertIn("image_base64", resp.get_json())

        resp = self.client.get(self._url("surface"), headers=headers)
        self.assertEqual(resp.status_code, 200, resp.get_json())
        self.assertIn("root", resp.get_json())

    # (b) a key without the scope is refused before the handler runs
    def test_api_key_without_the_scope_gets_403(self):
        headers = self._api_key_headers(["databases:read"])
        for suffix in ("capabilities", "frame", "surface"):
            resp = self.client.get(self._url(suffix), headers=headers)
            self.assertEqual(resp.status_code, 403,
                             f"{suffix}: {resp.status_code}")

    # (c) JWT callers are unaffected by the conversion
    def test_jwt_caller_still_gets_200(self):
        headers = self._jwt_headers()
        for suffix in ("capabilities", "frame", "surface"):
            resp = self.client.get(self._url(suffix), headers=headers)
            self.assertEqual(resp.status_code, 200,
                             f"{suffix}: {resp.status_code} {resp.get_json()}")

    # (d) no credentials at all
    def test_unauthenticated_gets_401(self):
        for suffix in ("capabilities", "frame", "surface"):
            resp = self.client.get(self._url(suffix))
            self.assertEqual(resp.status_code, 401,
                             f"{suffix}: {resp.status_code}")


if __name__ == "__main__":
    unittest.main()
