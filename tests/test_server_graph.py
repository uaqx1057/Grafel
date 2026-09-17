import atexit
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]

# Load server/app.py against a throwaway sqlite file so init() never touches
# a real grafel.db in the repo (same spec-loader pattern as test_server_config,
# plus a GRAFEL_DB override because this suite actually writes rows).
_TMP = tempfile.TemporaryDirectory()
_OLD_DB = os.environ.get("GRAFEL_DB")
os.environ["GRAFEL_DB"] = os.path.join(_TMP.name, "grafel-test.db")
try:
    SPEC = importlib.util.spec_from_file_location(
        "grafel_server_app_graph", ROOT / "server" / "app.py")
    server_app = importlib.util.module_from_spec(SPEC)
    assert SPEC.loader is not None
    SPEC.loader.exec_module(server_app)
finally:
    if _OLD_DB is None:
        os.environ.pop("GRAFEL_DB", None)
    else:
        os.environ["GRAFEL_DB"] = _OLD_DB


def _cleanup_tmp():
    try:
        _TMP.cleanup()
    except OSError:
        pass


atexit.register(_cleanup_tmp)

client = TestClient(server_app.app)
ADMIN = {"X-Admin-Token": server_app.ADMIN_TOKEN}


def issue_license(seats=1):
    r = client.post("/license/issue",
                    json={"plan": "pro", "days": 30, "seats": seats},
                    headers=ADMIN)
    assert r.status_code == 200, r.text
    return r.json()["key"]


class GraphOwnershipTests(unittest.TestCase):
    def test_put_then_get_same_license(self):
        key = issue_license()
        r = client.put("/graph/proj-same", json={"nodes": [1, 2]},
                       headers={"X-License-Key": key})
        self.assertEqual(r.status_code, 200)
        r = client.get("/graph/proj-same", headers={"X-License-Key": key})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["graph"], {"nodes": [1, 2]})

    def test_put_conflicting_owner_rejected_and_original_kept(self):
        key_a = issue_license()
        key_b = issue_license()
        r = client.put("/graph/proj-collide", json={"owner": "A"},
                       headers={"X-License-Key": key_a})
        self.assertEqual(r.status_code, 200)
        r = client.put("/graph/proj-collide", json={"owner": "B"},
                       headers={"X-License-Key": key_b})
        self.assertEqual(r.status_code, 409)
        # License A's data must be untouched.
        r = client.get("/graph/proj-collide", headers={"X-License-Key": key_a})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["graph"], {"owner": "A"})

    def test_get_other_owner_rejected(self):
        key_a = issue_license()
        key_b = issue_license()
        r = client.put("/graph/proj-private", json={"secret": True},
                       headers={"X-License-Key": key_a})
        self.assertEqual(r.status_code, 200)
        r = client.get("/graph/proj-private", headers={"X-License-Key": key_b})
        self.assertEqual(r.status_code, 403)

    def test_missing_graph_is_404(self):
        key = issue_license()
        r = client.get("/graph/proj-nonexistent", headers={"X-License-Key": key})
        self.assertEqual(r.status_code, 404)

    def test_no_license_is_402(self):
        r = client.put("/graph/proj-nolicense", json={})
        self.assertEqual(r.status_code, 402)
        r = client.get("/graph/proj-nolicense")
        self.assertEqual(r.status_code, 402)

    def test_reupload_by_owner_updates(self):
        key = issue_license()
        client.put("/graph/proj-update", json={"v": 1},
                   headers={"X-License-Key": key})
        r = client.put("/graph/proj-update", json={"v": 2},
                       headers={"X-License-Key": key})
        self.assertEqual(r.status_code, 200)
        r = client.get("/graph/proj-update", headers={"X-License-Key": key})
        self.assertEqual(r.json()["graph"], {"v": 2})


class UploadSizeCapTests(unittest.TestCase):
    def test_oversized_body_rejected(self):
        key = issue_license()
        old_cap = server_app.MAX_GRAPH_BYTES
        server_app.MAX_GRAPH_BYTES = 64
        try:
            r = client.put("/graph/proj-big", json={"blob": "x" * 200},
                           headers={"X-License-Key": key})
            self.assertEqual(r.status_code, 413)
            # Under the cap still works.
            r = client.put("/graph/proj-big", json={"ok": 1},
                           headers={"X-License-Key": key})
            self.assertEqual(r.status_code, 200)
        finally:
            server_app.MAX_GRAPH_BYTES = old_cap

    def test_oversized_content_length_rejected_before_parse(self):
        # A Content-Length header over the cap must 413 via the dependency,
        # BEFORE body parsing — the body here is tiny and wouldn't trip the
        # post-parse check (httpx keeps a caller-supplied Content-Length via
        # Headers.setdefault, so the header can lie independently of the body).
        key = issue_license()
        old_cap = server_app.MAX_GRAPH_BYTES
        server_app.MAX_GRAPH_BYTES = 64
        try:
            r = client.put("/graph/proj-clbig", content=b'{"ok": 1}',
                           headers={"X-License-Key": key,
                                    "Content-Type": "application/json",
                                    "Content-Length": "999999"})
            self.assertEqual(r.status_code, 413)
        finally:
            server_app.MAX_GRAPH_BYTES = old_cap

    def test_lying_small_content_length_still_caught_post_parse(self):
        # A client understating Content-Length bypasses the pre-parse check;
        # the post-parse size check remains as defense in depth.
        key = issue_license()
        old_cap = server_app.MAX_GRAPH_BYTES
        server_app.MAX_GRAPH_BYTES = 64
        try:
            body = b'{"blob": "' + b"x" * 200 + b'"}'
            r = client.put("/graph/proj-cllie", content=body,
                           headers={"X-License-Key": key,
                                    "Content-Type": "application/json",
                                    "Content-Length": "10"})
            self.assertEqual(r.status_code, 413)
        finally:
            server_app.MAX_GRAPH_BYTES = old_cap

    def test_reject_oversized_upload_dependency_unit(self):
        # Direct unit check of the dependency: oversized header raises 413,
        # absent or malformed headers fall through (post-parse check handles those).
        from fastapi import HTTPException

        class FakeRequest:
            def __init__(self, headers):
                self.headers = headers

        with self.assertRaises(HTTPException) as ctx:
            server_app.reject_oversized_upload(
                FakeRequest({"content-length": str(server_app.MAX_GRAPH_BYTES + 1)}))
        self.assertEqual(ctx.exception.status_code, 413)
        # Under the cap, absent, and malformed all pass through without raising.
        server_app.reject_oversized_upload(FakeRequest({"content-length": "10"}))
        server_app.reject_oversized_upload(FakeRequest({}))
        server_app.reject_oversized_upload(FakeRequest({"content-length": "banana"}))


class AdminTokenTests(unittest.TestCase):
    def test_wrong_token_rejected(self):
        r = client.get("/analytics/summary",
                       headers={"X-Admin-Token": "not-the-token"})
        self.assertEqual(r.status_code, 401)

    def test_missing_token_rejected_without_crash(self):
        r = client.get("/analytics/summary")
        self.assertEqual(r.status_code, 401)

    def test_require_admin_none_raises_401(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            server_app.require_admin(None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_require_admin_accepts_correct_token(self):
        server_app.require_admin(server_app.ADMIN_TOKEN)


class SeatLimitTests(unittest.TestCase):
    def test_seat_limit_sequential(self):
        key = issue_license(seats=1)
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "machine-a"})
        self.assertTrue(r.json()["valid"])
        # Second machine exceeds the single seat.
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "machine-b"})
        body = r.json()
        self.assertFalse(body["valid"])
        self.assertEqual(body.get("reason"), "seat limit reached")
        # Same machine re-activating is not wrongly rejected.
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "machine-a"})
        self.assertTrue(r.json()["valid"])
        # Exactly one activation row was recorded.
        from contextlib import closing
        with closing(server_app.db()) as c:
            n = c.execute("SELECT COUNT(*) n FROM activations WHERE key=?",
                          (key,)).fetchone()["n"]
        self.assertEqual(n, 1)

    def test_validate_without_machine_id(self):
        key = issue_license(seats=1)
        r = client.post("/license/validate", json={"key": key})
        self.assertTrue(r.json()["valid"])

    def test_multi_seat_allows_second_machine(self):
        key = issue_license(seats=2)
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "m1"})
        self.assertTrue(r.json()["valid"])
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "m2"})
        self.assertTrue(r.json()["valid"])
        r = client.post("/license/validate",
                        json={"key": key, "machine_id": "m3"})
        self.assertFalse(r.json()["valid"])

    def test_unknown_key_invalid(self):
        r = client.post("/license/validate",
                        json={"key": "GRAFEL-NOPE", "machine_id": "m1"})
        self.assertFalse(r.json()["valid"])


if __name__ == "__main__":
    unittest.main()
