"""backend/surface.py produces valid surface-v1 documents.

The schema is a vendored copy of vela-contracts' surface-v1.schema.json;
refresh it when the contract changes.

Run with: python -m unittest discover -s tests
"""
import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("surface", ROOT / "backend" / "surface.py")
surface = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(surface)

VALIDATOR = Draft202012Validator(json.loads((ROOT / "tests" / "surface-v1.schema.json").read_text(encoding="utf-8")))
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)

# Shapes as serverkit-agent returns them (internal/metrics, internal/docker,
# internal/agent/systemd_handlers.go).
INFO = {"hostname": "web-01", "os": "linux", "platform": "ubuntu", "platform_version": "24.04",
        "kernel_version": "6.8.0", "architecture": "x86_64", "cpu_model": "AMD EPYC", "cpu_cores": 8,
        "cpu_threads": 16, "total_memory": 17179869184, "total_disk": 107374182400}
METRICS = {"cpu_percent": 23.4, "memory_percent": 81.2, "disk_total": 107374182400,
           "disk_used": 99857989632, "disk_percent": 93.0, "uptime": 86400}
PROCESSES = [{"pid": 1, "name": "systemd", "cpu_percent": 0.1, "mem_percent": 0.2},
             {"pid": 900, "name": "postgres", "cpu_percent": 12.5, "mem_percent": 8.1},
             {"pid": 901, "name": "nginx", "cpu_percent": 3.0, "mem_percent": 1.0}]
CONTAINERS = [{"id": "a1b2c3d4e5f6", "name": "app", "image": "app:1", "state": "running", "status": "Up 2 hours"},
              {"id": "0f9e8d7c6b5a", "name": "worker", "image": "app:1", "state": "exited", "status": "Exited (1)"}]
UNITS = [{"unit": "nginx.service", "load": "loaded", "active": "active", "sub": "running", "description": "nginx"},
         {"unit": "backup.service", "load": "loaded", "active": "failed", "sub": "failed", "description": "Backups"},
         {"unit": "idle.service", "load": "loaded", "active": "inactive", "sub": "dead"}]


def full(**overrides):
    args = dict(server_name="web-01", info=INFO, metrics=METRICS, processes=PROCESSES,
                containers=CONTAINERS, units=UNITS, cpu_history=[10, 20, 30], can_act=True, now=NOW)
    args.update(overrides)
    return surface.build_server_surface(**args)


def windows(doc):
    return {w["id"]: w for w in doc["root"]["windows"]}


class SurfaceTests(unittest.TestCase):
    def assertValid(self, doc):
        errors = sorted(VALIDATOR.iter_errors(doc), key=str)
        self.assertEqual(errors, [], errors[:1])

    def test_a_full_server_is_a_valid_desktop(self):
        doc = full()
        self.assertValid(doc)
        self.assertEqual(doc["root"]["type"], "desktop")
        self.assertEqual(list(windows(doc)), ["system", "services", "containers", "processes", "storage"])
        self.assertEqual(doc["subtitle"], "Ubuntu 24.04 · x86_64")

    def test_offline_and_empty_agents_still_validate(self):
        self.assertValid(surface.build_server_surface(server_name="web-01", offline=True, now=NOW))
        doc = surface.build_server_surface(server_name="web-01", now=NOW)
        self.assertValid(doc)
        self.assertEqual(list(windows(doc)), ["system"])

    def test_processes_are_ranked_by_cpu_and_read_mem_percent(self):
        rows = windows(full())["processes"]["children"][0]["rows"]
        self.assertEqual([r["name"] for r in rows], ["postgres", "nginx", "systemd"])
        self.assertEqual(rows[0]["mem"], 8.1)

    def test_services_show_failed_first_and_skip_dead_units(self):
        rows = windows(full())["services"]["children"][0]["rows"]
        self.assertEqual([r["label"] for r in rows], ["backup.service", "nginx.service"])
        self.assertEqual(rows[0]["tone"], "bad")

    def test_buttons_only_for_users_who_can_act_and_only_declared_actions(self):
        doc = full()
        self.assertEqual({a["id"] for a in doc["actions"]}, {"restart-container", "restart-service"})
        buttons = windows(doc)["containers"]["children"][1]["children"]
        self.assertEqual([b["input"] for b in buttons], [{"container": "a1b2c3d4e5f6"}])  # not the exited one

        viewer = full(can_act=False)
        self.assertValid(viewer)
        self.assertNotIn("actions", viewer)
        self.assertNotIn('"button"', json.dumps(viewer))

    def test_disk_pressure_is_flagged(self):
        storage = windows(full())["storage"]["children"][0]
        self.assertEqual(storage["tone"], "bad")
        self.assertEqual(storage["caption"], "93.0 GB of 100.0 GB used")

    def test_hostile_agent_values_stay_inside_the_contract(self):
        doc = full(info={**INFO, "hostname": "x" * 500, "cpu_model": "<script>" * 100},
                   processes=[{"name": None, "cpu_percent": "high", "mem_percent": True}] * 50,
                   containers=[{"id": "../../etc", "name": "evil", "state": "running"}],
                   units=[{"unit": "x;rm -rf /.service", "active": "failed"}])
        self.assertValid(doc)
        self.assertNotIn("actions", doc)  # nothing safe to act on


if __name__ == "__main__":
    unittest.main()
