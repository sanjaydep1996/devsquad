# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Only DevSquad's own pages may use the local server. Talks to a real server over a real socket."""

import http.client
import json
import pathlib
import tempfile
import threading
import unittest

from devsquad.server.server import start_studio_server

EVIL = "https://evil.example"


class TestLocalOnlyServer(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = start_studio_server(pathlib.Path(tmp.name), port=0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def call(self, path, method="GET", headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
        finally:
            conn.close()

    def post(self, headers=None):
        return self.call("/api/spawn", "POST", headers=headers, body=json.dumps({"agent": "apex", "task": ""}))

    def test_listens_on_this_computer_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_another_website_cannot_post(self):
        for origin in (EVIL, "null", "http://localhost:1"):
            status, _, _ = self.post({"Origin": origin, "Content-Type": "text/plain"})
            self.assertEqual(status, 403, origin)

    def test_its_own_page_can_post(self):
        for origin in (f"http://localhost:{self.port}", f"http://127.0.0.1:{self.port}"):
            self.assertNotEqual(self.post({"Origin": origin})[0], 403, origin)

    def test_command_line_tools_can_post(self):
        self.assertNotEqual(self.post()[0], 403)

    def test_dns_rebinding_is_refused(self):
        headers = {"Host": f"evil.example:{self.port}"}
        self.assertEqual(self.call("/", headers=headers)[0], 403)
        self.assertEqual(self.post(headers)[0], 403)

    def test_no_response_is_readable_by_other_websites(self):
        for path in ("/", "/data/usage.json", "/api/status"):
            _, headers, _ = self.call(path, headers={"Origin": EVIL})
            self.assertNotIn("access-control-allow-origin", headers, path)
        _, headers, _ = self.post({"Origin": f"http://localhost:{self.port}"})
        self.assertNotIn("access-control-allow-origin", headers)

    def test_fastapi_app_has_no_open_cors(self):
        src = (pathlib.Path(__file__).parent.parent / "devsquad/server/fastapi_app.py").read_text(encoding="utf-8")
        self.assertNotIn('allow_origins=["*"]', src)
        self.assertIn("is_local_host", src)
        self.assertIn("origin_matches_host", src)

    def test_fastapi_app_starts_and_refuses_other_websites(self):
        try:
            from fastapi.testclient import TestClient
        except Exception:
            self.skipTest("fastapi is not installed")
        from devsquad.server.fastapi_app import create_app
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(pathlib.Path(tmp)), base_url="http://localhost:8080")
            path = "/api/v1/chaos/inject"
            self.assertNotEqual(client.post(path, json={}, headers={"Origin": "http://localhost:8080"}).status_code, 403)
            self.assertEqual(client.post(path, json={}, headers={"Origin": EVIL}).status_code, 403)
            self.assertEqual(client.get("/", headers={"Host": "evil.example"}).status_code, 403)
            self.assertNotIn("access-control-allow-origin", client.get("/", headers={"Origin": EVIL}).headers)
            with self.assertRaises(Exception):
                with client.websocket_connect("ws://localhost:8080/ws/terminal/apex", headers={"Origin": EVIL}):
                    pass
            with client.websocket_connect("ws://localhost:8080/ws/terminal/apex", headers={"Origin": "http://localhost:8080"}) as ws:
                self.assertIn("DEVSQUAD", ws.receive_text())


if __name__ == "__main__":
    unittest.main()
