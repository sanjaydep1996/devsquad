# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Project files: upload, list, download and delete planning material, and hand readable ones to the agents."""

import http.client
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.parse

from devsquad.core.files import MAX_FILE_BYTES, FileRejected, ProjectFiles
from devsquad.server.server import start_studio_server

PDF = b"%PDF-1.4\n\x00\xff\xfe binary bytes \x80\x81"


class TestProjectFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.files = ProjectFiles(self.root)

    def test_saves_inside_the_ignored_devsquad_folder(self):
        info = self.files.save("brief.pdf", PDF)
        self.assertEqual(info["name"], "brief.pdf")
        self.assertEqual(info["size"], len(PDF))
        self.assertEqual((self.root / ".devsquad" / "files" / "brief.pdf").read_bytes(), PDF)

    def test_a_hostile_name_cannot_leave_the_folder(self):
        for name in ("../../evil.sh", "/etc/passwd", "..\\..\\evil.bat", "a/b/c.txt"):
            info = self.files.save(name, b"x")
            saved = self.files.path(info["name"])
            self.assertEqual(saved.parent, self.files.folder, name)

    def test_hidden_and_empty_names_are_refused(self):
        for name in ("", ".env", "..", "   "):
            with self.assertRaises(FileRejected, msg=name):
                self.files.save(name, b"x")

    def test_a_file_over_the_limit_is_refused(self):
        with self.assertRaises(FileRejected):
            self.files.save("big.bin", b"x" * (MAX_FILE_BYTES + 1))

    def test_lists_newest_first_and_deletes(self):
        self.files.save("a.txt", b"one")
        self.files.save("b.png", b"two")
        self.assertEqual({f["name"] for f in self.files.list()}, {"a.txt", "b.png"})
        self.assertTrue(self.files.delete("a.txt"))
        self.assertFalse(self.files.delete("a.txt"))
        self.assertEqual([f["name"] for f in self.files.list()], ["b.png"])

    def test_agents_get_text_files_in_full_and_other_files_by_name(self):
        self.files.save("prd.md", b"# Login\nUsers sign in with email.")
        self.files.save("mock.png", b"\x89PNG....")
        self.files.save("brief.pdf", PDF)
        text = self.files.context_for(["prd.md", "mock.png", "brief.pdf", "missing.txt"])
        self.assertIn("Users sign in with email.", text)
        self.assertIn("mock.png", text)
        self.assertIn("brief.pdf", text)
        self.assertIn("can't be read", text)
        self.assertNotIn("missing.txt", text)
        self.assertNotIn("PNG....", text)

    def test_long_text_is_cut_so_it_fits_a_local_model(self):
        self.files.save("huge.txt", b"word " * 50000)
        self.assertLess(len(self.files.context_for(["huge.txt"])), 20000)

    def test_no_files_means_no_context(self):
        self.assertEqual(self.files.context_for([]), "")


class TestFilesOverHttp(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.server = start_studio_server(self.root, port=0)
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

    def upload(self, name, data, headers=None):
        return self.call("/api/files?name=" + urllib.parse.quote(name), "POST", headers=headers, body=data)

    def test_binary_upload_downloads_back_byte_for_byte(self):
        status, _, body = self.upload("Product brief v2.pdf", PDF)
        self.assertEqual(status, 200)
        name = json.loads(body)["file"]["name"]
        status, headers, data = self.call("/api/files/" + urllib.parse.quote(name))
        self.assertEqual(status, 200)
        self.assertEqual(data, PDF)

    def test_downloads_are_never_rendered_as_a_page(self):
        # An uploaded .html file must not run as a page on the studio's own address.
        self.upload("evil.html", b"<script>alert(1)</script>")
        _, headers, _ = self.call("/api/files/evil.html")
        self.assertIn("attachment", headers["content-disposition"])
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertEqual(headers["x-content-type-options"], "nosniff")

    def test_lists_uploaded_files(self):
        self.upload("a.txt", b"hello")
        status, _, body = self.call("/api/files")
        self.assertEqual(status, 200)
        self.assertEqual([f["name"] for f in json.loads(body)["files"]], ["a.txt"])

    def test_delete_removes_the_file(self):
        self.upload("a.txt", b"hello")
        self.assertEqual(self.call("/api/files/a.txt", "DELETE")[0], 200)
        self.assertEqual(self.call("/api/files/a.txt")[0], 404)

    def test_too_large_is_refused_without_reading_it(self):
        status, _, _ = self.call("/api/files?name=big.bin", "POST", headers={"Content-Length": str(MAX_FILE_BYTES + 1)}, body=b"")
        self.assertEqual(status, 413)

    def test_bad_names_are_a_clear_error(self):
        status, _, body = self.upload(".env", b"SECRET=1")
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))

    def test_another_website_cannot_upload_or_delete(self):
        evil = {"Origin": "https://evil.example"}
        self.assertEqual(self.upload("x.txt", b"x", headers=evil)[0], 403)
        self.upload("keep.txt", b"keep")
        self.assertEqual(self.call("/api/files/keep.txt", "DELETE", headers=evil)[0], 403)
        self.assertEqual(self.call("/api/files/keep.txt")[0], 200)

    def test_traversal_in_the_download_path_finds_nothing(self):
        (self.root / "secret.txt").write_text("PRIVATE")
        for path in ("/api/files/..%2f..%2fsecret.txt", "/api/files/../../secret.txt"):
            status, _, body = self.call(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"PRIVATE", body)


if __name__ == "__main__":
    unittest.main()
