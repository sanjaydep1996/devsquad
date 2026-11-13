# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Greenfield bootstrapper: one prompt becomes a working FastAPI + SQLite app with login, a web page and tests.

The model, when one is running, only decides what the app is about: its name, main record and fields.
The code itself comes from tested templates, so the app runs and its tests pass every time.
New apps are staged in .devsquad/greenfield/<slug>/ and copied out only when the person approves.
"""

import datetime
import json
import keyword
import pathlib
import re
import shutil
from typing import Any, Dict, List, Optional

from .planner import _first_json_object

TYPES = {"str": ("TEXT", "str", '""', '"Sample"'), "int": ("INTEGER", "int", "0", "3"),
         "float": ("REAL", "float", "0.0", "2.5"), "bool": ("INTEGER", "bool", "False", "True")}
KNOWN = [  # keyword, record, plural, fields
    (("inventory", "stock", "warehouse", "product"), "item", "items", [("name", "str"), ("sku", "str"), ("quantity", "int"), ("price", "float")]),
    (("todo", "to-do", "task"), "task", "tasks", [("title", "str"), ("notes", "str"), ("done", "bool")]),
    (("blog", "article", "post"), "post", "posts", [("title", "str"), ("body", "str"), ("published", "bool")]),
    (("note", "journal"), "note", "notes", [("title", "str"), ("body", "str")]),
    (("crm", "contact", "customer", "lead"), "contact", "contacts", [("name", "str"), ("email", "str"), ("company", "str")]),
    (("expense", "budget", "spending"), "expense", "expenses", [("description", "str"), ("amount", "float"), ("category", "str")]),
    (("book", "library", "reading"), "book", "books", [("title", "str"), ("author", "str"), ("pages", "int"), ("read", "bool")]),
    (("event", "booking", "appointment"), "booking", "bookings", [("title", "str"), ("date", "str"), ("guests", "int")]),
    (("recipe", "cooking"), "recipe", "recipes", [("name", "str"), ("ingredients", "str"), ("minutes", "int")]),
]


class BootstrapError(ValueError):
    """The request can't be carried out. The message is safe to show to the person."""


def _ident(name: Any) -> Optional[str]:
    n = re.sub(r"[^a-z0-9_]+", "_", str(name or "").strip().lower()).strip("_")
    if not n or n[0].isdigit() or keyword.iskeyword(n) or n in ("id", "owner_id", "user", "users", "tokens"):
        return None
    return n[:30]


class Bootstrapper:
    def __init__(self, root: Optional[pathlib.Path] = None):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.stage = self.root / ".devsquad" / "greenfield"

    # ----- what to build -----
    def design(self, prompt: str, provider: Any = None) -> Dict[str, Any]:
        prompt = re.sub(r"\s+", " ", prompt or "").strip()[:500]
        if not prompt:
            raise BootstrapError("Describe the app you want, for example: an inventory app with login.")
        spec = self._from_model(prompt, provider) if provider is not None and "template" not in getattr(provider, "provider_name", "template") else None
        source = getattr(provider, "model", "model") if spec else "keywords"
        if not spec:
            spec = self._from_keywords(prompt)
        spec.update(prompt=prompt, source=source)
        return spec

    def _from_keywords(self, prompt: str) -> Dict[str, Any]:
        low = prompt.lower()
        record, plural, fields = "item", "items", [("name", "str"), ("description", "str")]
        for words, r, p, f in KNOWN:
            if any(re.search(rf"\b{re.escape(w)}", low) for w in words):
                record, plural, fields = r, p, f
                break
        m = re.search(r"\b(?:build|create|make|start)\s+(?:me\s+)?(?:an?|the)?\s*(.+?)\s+(?:app|application|system|tool|website|site|platform|tracker|manager)\b", low)
        name = (m.group(1) if m else plural).strip()
        name = re.sub(r"\b(simple|small|basic|new|full[- ]stack|web)\b", "", name).strip() or plural
        return {"app_name": " ".join(w.capitalize() for w in name.split()[:4]), "record": record, "plural": plural,
                "fields": [{"name": n, "type": t} for n, t in fields]}

    def _from_model(self, prompt: str, provider: Any) -> Optional[Dict[str, Any]]:
        ask = ("Design the data for this app. Reply with only JSON: "
               '{"app_name": "Inventory Manager", "record": "item", "plural": "items", '
               '"fields": [{"name": "name", "type": "str"}]}. Types are str, int, float or bool. '
               "Use 2 to 6 fields, lowercase snake_case names.\nAPP: " + prompt)
        try:
            data = _first_json_object(provider.complete(ask, system="You reply with JSON only.", max_tokens=600).text or "")
        except Exception:
            return None
        if not data:
            return None
        record, plural = _ident(data.get("record")), _ident(data.get("plural"))
        fields, seen = [], set()
        for f in data.get("fields") or []:
            name = _ident((f or {}).get("name")) if isinstance(f, dict) else None
            if name and name not in seen and f.get("type") in TYPES:
                fields.append({"name": name, "type": f["type"]})
                seen.add(name)
        if not record or not plural or record == plural or not 1 <= len(fields) <= 8 or fields[0]["type"] != "str":
            return None
        return {"app_name": re.sub(r"[^\w &-]", "", str(data.get("app_name") or plural.title()))[:40].strip() or plural.title(),
                "record": record, "plural": plural, "fields": fields}

    # ----- the code -----
    def generate(self, prompt: str, provider: Any = None) -> Dict[str, Any]:
        spec = self.design(prompt, provider)
        slug = re.sub(r"[^a-z0-9]+", "-", spec["app_name"].lower()).strip("-")[:40] or "app"
        files = self._files(spec)
        out = self.stage / slug
        if out.exists():
            shutil.rmtree(out)
        for rel, content in files.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_text(content, encoding="utf-8")
        (out / ".devsquad-spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        return {"slug": slug, "spec": spec, "staged_at": out.relative_to(self.root).as_posix(), "files": sorted(files),
                "run": "pip install -r requirements.txt && uvicorn app.main:app --reload",
                "test": "pip install -r requirements.txt && python -m unittest discover -s tests -v"}

    def apply(self, slug: str, target: str) -> Dict[str, Any]:
        """Copies a staged app into a new or empty folder. It never writes into a folder that has files."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,40}", slug or ""):
            raise BootstrapError("That app isn't staged.")
        source = self.stage / slug
        if not source.is_dir():
            raise BootstrapError("That app isn't staged. Generate it again.")
        if not (target or "").strip():
            raise BootstrapError("Choose a folder for the new app.")
        dest = pathlib.Path(target).expanduser()
        if not dest.is_absolute():
            dest = self.root.parent / dest
        dest = dest.resolve()
        if dest == self.root or self.root in dest.parents and ".devsquad" in dest.parts:
            raise BootstrapError("Choose a folder outside this project's .devsquad folder.")
        if dest.exists() and (not dest.is_dir() or any(dest.iterdir())):
            raise BootstrapError(f"{dest} already has files in it. Choose a new or empty folder.")
        shutil.copytree(source, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".devsquad-spec.json"))
        return {"path": str(dest), "files": sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())}

    def _files(self, spec: Dict[str, Any]) -> Dict[str, str]:
        rec, plural, fields, name = spec["record"], spec["plural"], spec["fields"], spec["app_name"]
        Rec = "".join(w.capitalize() for w in rec.split("_"))
        cols = ", ".join(f"{f['name']} {TYPES[f['type']][0]}" + (" NOT NULL" if i == 0 else "") for i, f in enumerate(fields))
        model_fields = "\n".join(f"    {f['name']}: {TYPES[f['type']][1]}" + ("" if i == 0 else f" = {TYPES[f['type']][2]}") for i, f in enumerate(fields))
        names = [f["name"] for f in fields]
        bools = [f["name"] for f in fields if f["type"] == "bool"]
        sample = ", ".join(f'"{f["name"]}": {TYPES[f["type"]][3]}' for f in fields)
        first = fields[0]["name"]
        today = datetime.date.today().isoformat()

        main = MAIN_PY.replace("@@REC@@", rec).replace("@@RECCLASS@@", Rec).replace("@@PLURAL@@", plural) \
            .replace("@@APPNAME@@", name).replace("@@COLUMNS@@", cols).replace("@@MODEL_FIELDS@@", model_fields) \
            .replace("@@FIELDS@@", repr(names)).replace("@@BOOLS@@", repr(bools))
        tests = TESTS_PY.replace("@@PLURAL@@", plural).replace("@@SAMPLE@@", sample).replace("@@FIRST@@", first)
        page = INDEX_HTML.replace("@@APPNAME@@", name).replace("@@PLURAL@@", plural).replace("@@REC@@", rec) \
            .replace("@@FIELDS_JSON@@", json.dumps(fields))
        return {
            "app/__init__.py": "",
            "app/main.py": main,
            "app/static/index.html": page,
            "tests/__init__.py": "",
            "tests/test_app.py": tests,
            "requirements.txt": "fastapi>=0.110\nuvicorn>=0.29\nhttpx>=0.27\n",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\n*.db\n.env\n",
            "README.md": f"# {name}\n\nA FastAPI + SQLite app with sign-up, login and a page to manage your {plural}. Built with DevSquad.\n\n"
                         "## Run it\n\n```bash\npython -m venv .venv && source .venv/bin/activate\npip install -r requirements.txt\n"
                         "uvicorn app.main:app --reload\n```\n\nOpen http://localhost:8000.\n\n## Test it\n\n```bash\npython -m unittest discover -s tests -v\n```\n\n"
                         "## Settings\n\n- `APP_DB`: where the SQLite file lives (default `app.db`).\n",
            "docs/adr/0001-initial-architecture.md": f"# 0001. Initial architecture\n\nDate: {today}\nStatus: Accepted\n\n## Context\n\n{spec['prompt']}\n\n"
                f"## Decision\n\n- FastAPI for the API, SQLite for storage, and one static page for the interface.\n- Sign-up and login with salted PBKDF2 password hashes and random bearer tokens.\n"
                f"- Each user sees and changes only their own {plural}.\n- Fields of a {rec}: " + ", ".join(f"`{f['name']}` ({f['type']})" for f in fields) + ".\n\n"
                "## Consequences\n\n- No external services are needed to run or test it.\n- SQLite suits one server. Move to Postgres before running several copies.\n",
        }


MAIN_PY = '''"""@@APPNAME@@: a FastAPI + SQLite app with login. Generated by DevSquad."""

import hashlib
import os
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

FIELDS = @@FIELDS@@
BOOL_FIELDS = @@BOOLS@@
STATIC = Path(__file__).parent / "static"


class Credentials(BaseModel):
    email: str
    password: str


class @@RECCLASS@@In(BaseModel):
@@MODEL_FIELDS@@


def _hash(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000).hex()


def create_app(db_path: str = "app.db") -> FastAPI:
    app = FastAPI(title="@@APPNAME@@")

    def db() -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    with closing(db()) as conn, conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, salt BLOB NOT NULL, hash TEXT NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id))")
        conn.execute("CREATE TABLE IF NOT EXISTS @@PLURAL@@ (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), @@COLUMNS@@)")

    def user_id(authorization: Optional[str]) -> int:
        token = (authorization or "").removeprefix("Bearer ").strip()
        with closing(db()) as conn:
            row = conn.execute("SELECT user_id FROM tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Log in first.")
        return row["user_id"]

    def as_dict(row: sqlite3.Row) -> dict:
        out = {"id": row["id"], **{f: row[f] for f in FIELDS}}
        for f in BOOL_FIELDS:
            out[f] = bool(out[f])
        return out

    @app.post("/api/signup", status_code=201)
    def signup(body: Credentials):
        email = body.email.strip().lower()
        if "@" not in email or len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Use a valid email and a password of at least 8 characters.")
        salt = secrets.token_bytes(16)
        try:
            with closing(db()) as conn, conn:
                conn.execute("INSERT INTO users (email, salt, hash) VALUES (?, ?, ?)", (email, salt, _hash(body.password, salt)))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="That email already has an account.")
        return {"ok": True}

    @app.post("/api/login")
    def login(body: Credentials):
        with closing(db()) as conn, conn:
            user = conn.execute("SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),)).fetchone()
            if not user or not secrets.compare_digest(user["hash"], _hash(body.password, user["salt"])):
                raise HTTPException(status_code=401, detail="Wrong email or password.")
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO tokens (token, user_id) VALUES (?, ?)", (token, user["id"]))
        return {"token": token}

    @app.get("/api/@@PLURAL@@")
    def list_@@PLURAL@@(authorization: Optional[str] = Header(None)):
        uid = user_id(authorization)
        with closing(db()) as conn:
            rows = conn.execute("SELECT * FROM @@PLURAL@@ WHERE owner_id = ? ORDER BY id DESC", (uid,)).fetchall()
        return [as_dict(r) for r in rows]

    @app.post("/api/@@PLURAL@@", status_code=201)
    def create_@@REC@@(body: @@RECCLASS@@In, authorization: Optional[str] = Header(None)):
        uid = user_id(authorization)
        values = body.model_dump()
        with closing(db()) as conn, conn:
            cur = conn.execute(
                f"INSERT INTO @@PLURAL@@ (owner_id, {', '.join(FIELDS)}) VALUES (?, {', '.join('?' for _ in FIELDS)})",
                (uid, *[values[f] for f in FIELDS]),
            )
            row = conn.execute("SELECT * FROM @@PLURAL@@ WHERE id = ?", (cur.lastrowid,)).fetchone()
        return as_dict(row)

    @app.put("/api/@@PLURAL@@/{record_id}")
    def update_@@REC@@(record_id: int, body: @@RECCLASS@@In, authorization: Optional[str] = Header(None)):
        uid = user_id(authorization)
        values = body.model_dump()
        with closing(db()) as conn, conn:
            cur = conn.execute(
                f"UPDATE @@PLURAL@@ SET {', '.join(f + ' = ?' for f in FIELDS)} WHERE id = ? AND owner_id = ?",
                (*[values[f] for f in FIELDS], record_id, uid),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Not found.")
            row = conn.execute("SELECT * FROM @@PLURAL@@ WHERE id = ?", (record_id,)).fetchone()
        return as_dict(row)

    @app.delete("/api/@@PLURAL@@/{record_id}", status_code=204)
    def delete_@@REC@@(record_id: int, authorization: Optional[str] = Header(None)):
        uid = user_id(authorization)
        with closing(db()) as conn, conn:
            cur = conn.execute("DELETE FROM @@PLURAL@@ WHERE id = ? AND owner_id = ?", (record_id, uid))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found.")
        return Response(status_code=204)

    @app.get("/")
    def home():
        return FileResponse(STATIC / "index.html")

    return app


app = create_app(os.getenv("APP_DB", "app.db"))
'''

TESTS_PY = '''import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app

SAMPLE = {@@SAMPLE@@}


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.client = TestClient(create_app(os.path.join(self.tmp.name, "test.db")))

    def tearDown(self):
        self.tmp.cleanup()

    def login(self, email="ada@example.com", password="correct horse"):
        self.client.post("/api/signup", json={"email": email, "password": password})
        token = self.client.post("/api/login", json={"email": email, "password": password}).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def test_home_page_loads(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_you_must_log_in(self):
        self.assertEqual(self.client.get("/api/@@PLURAL@@").status_code, 401)

    def test_a_wrong_password_is_refused(self):
        self.login()
        self.assertEqual(self.client.post("/api/login", json={"email": "ada@example.com", "password": "wrong one"}).status_code, 401)

    def test_short_passwords_are_refused(self):
        self.assertEqual(self.client.post("/api/signup", json={"email": "a@example.com", "password": "short"}).status_code, 400)

    def test_create_list_update_and_delete(self):
        auth = self.login()
        created = self.client.post("/api/@@PLURAL@@", json=SAMPLE, headers=auth)
        self.assertEqual(created.status_code, 201)
        record = created.json()
        self.assertEqual([r["id"] for r in self.client.get("/api/@@PLURAL@@", headers=auth).json()], [record["id"]])
        changed = dict(SAMPLE, @@FIRST@@="Changed")
        self.assertEqual(self.client.put(f"/api/@@PLURAL@@/{record['id']}", json=changed, headers=auth).json()["@@FIRST@@"], "Changed")
        self.assertEqual(self.client.delete(f"/api/@@PLURAL@@/{record['id']}", headers=auth).status_code, 204)
        self.assertEqual(self.client.get("/api/@@PLURAL@@", headers=auth).json(), [])

    def test_people_only_see_their_own(self):
        ada = self.login()
        record = self.client.post("/api/@@PLURAL@@", json=SAMPLE, headers=ada).json()
        bob = self.login("bob@example.com")
        self.assertEqual(self.client.get("/api/@@PLURAL@@", headers=bob).json(), [])
        self.assertEqual(self.client.delete(f"/api/@@PLURAL@@/{record['id']}", headers=bob).status_code, 404)


if __name__ == "__main__":
    unittest.main()
'''

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@APPNAME@@</title>
<style>
  :root { --bg: #f6f5f1; --card: #fff; --ink: #1d1f27; --dim: #6b6657; --line: #e3ddd0; --accent: #b4580a; }
  @media (prefers-color-scheme: dark) { :root { --bg: #0d1018; --card: #161b27; --ink: #edf0f7; --dim: #8f99b0; --line: #273046; --accent: #ffb44c; } }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font: 15px/1.5 system-ui, sans-serif; }
  main { max-width: 860px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 26px; margin: 0 0 16px; }
  .card { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
  form { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 10px; align-items: end; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--dim); }
  input { font: inherit; padding: 9px 10px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); color: var(--ink); min-height: 40px; }
  input[type=checkbox] { min-height: 0; width: 20px; height: 20px; }
  button { font: inherit; font-weight: 600; min-height: 40px; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--accent); background: var(--accent); color: #fff; cursor: pointer; }
  button.ghost { background: transparent; color: var(--ink); border-color: var(--line); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; overflow-wrap: anywhere; }
  th { font-size: 12px; color: var(--dim); text-transform: uppercase; letter-spacing: .04em; }
  #msg { min-height: 22px; color: var(--accent); }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
  @media (max-width: 560px) { thead { display: none; } tr { display: block; border-bottom: 1px solid var(--line); padding: 6px 0; } td { display: block; border: 0; padding: 2px 0; } }
</style>
</head>
<body>
<main>
  <div class="row"><h1>@@APPNAME@@</h1><button class="ghost" id="logout" hidden>Log out</button></div>
  <p id="msg" role="status"></p>
  <section class="card" id="auth">
    <form id="authForm">
      <label>Email<input name="email" type="email" required autocomplete="email"></label>
      <label>Password<input name="password" type="password" minlength="8" required autocomplete="current-password"></label>
      <button type="submit" data-mode="login">Log in</button>
      <button type="submit" class="ghost" data-mode="signup">Sign up</button>
    </form>
  </section>
  <section class="card" id="app" hidden>
    <form id="addForm"></form>
  </section>
  <section class="card" id="listCard" hidden>
    <table><thead id="head"></thead><tbody id="rows"></tbody></table>
  </section>
</main>
<script>
const FIELDS = @@FIELDS_JSON@@;
let token = sessionStorage.getItem("token") || "";
const $ = s => document.querySelector(s);
const say = t => { $("#msg").textContent = t; };
const label = n => n.replace(/_/g, " ").replace(/^./, c => c.toUpperCase());
async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: "Bearer " + token } : {}) } });
  if (res.status === 401 && token) { token = ""; sessionStorage.removeItem("token"); show(); }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && data.detail) || "Something went wrong.");
  return data;
}
function show() {
  $("#auth").hidden = !!token; $("#app").hidden = $("#listCard").hidden = $("#logout").hidden = !token;
  if (token) load();
}
function valueOf(f, input) { return f.type === "bool" ? input.checked : f.type === "int" ? parseInt(input.value || "0", 10) : f.type === "float" ? parseFloat(input.value || "0") : input.value; }
function buildForm() {
  const form = $("#addForm");
  FIELDS.forEach((f, i) => {
    const l = document.createElement("label"); l.textContent = label(f.name);
    const input = document.createElement("input"); input.name = f.name;
    input.type = f.type === "bool" ? "checkbox" : f.type === "str" ? "text" : "number";
    if (f.type === "float") input.step = "any";
    if (i === 0) input.required = true;
    l.appendChild(input); form.appendChild(l);
  });
  const b = document.createElement("button"); b.type = "submit"; b.textContent = "Add @@REC@@"; form.appendChild(b);
  $("#head").innerHTML = "<tr>" + FIELDS.map(f => "<th></th>").join("") + "<th></th></tr>";
  $("#head").querySelectorAll("th").forEach((th, i) => { th.textContent = FIELDS[i] ? label(FIELDS[i].name) : ""; });
}
async function load() {
  try {
    const items = await api("/api/@@PLURAL@@");
    const rows = $("#rows"); rows.textContent = "";
    if (!items.length) { const tr = rows.insertRow(); const td = tr.insertCell(); td.colSpan = FIELDS.length + 1; td.textContent = "No @@PLURAL@@ yet."; }
    items.forEach(item => {
      const tr = rows.insertRow();
      FIELDS.forEach(f => { tr.insertCell().textContent = f.type === "bool" ? (item[f.name] ? "Yes" : "No") : item[f.name]; });
      const del = document.createElement("button"); del.className = "ghost"; del.textContent = "Delete";
      del.onclick = async () => { await api("/api/@@PLURAL@@/" + item.id, { method: "DELETE" }); load(); };
      tr.insertCell().appendChild(del);
    });
  } catch (e) { say(e.message); }
}
$("#authForm").addEventListener("submit", async e => {
  e.preventDefault();
  const mode = e.submitter ? e.submitter.dataset.mode : "login";
  const body = JSON.stringify({ email: e.target.email.value, password: e.target.password.value });
  try {
    if (mode === "signup") await api("/api/signup", { method: "POST", body });
    token = (await api("/api/login", { method: "POST", body })).token;
    sessionStorage.setItem("token", token); say(""); show();
  } catch (err) { say(err.message); }
});
$("#addForm").addEventListener("submit", async e => {
  e.preventDefault();
  const body = Object.fromEntries(FIELDS.map(f => [f.name, valueOf(f, e.target[f.name])]));
  try { await api("/api/@@PLURAL@@", { method: "POST", body: JSON.stringify(body) }); e.target.reset(); say(""); load(); } catch (err) { say(err.message); }
});
$("#logout").onclick = () => { token = ""; sessionStorage.removeItem("token"); show(); };
buildForm(); show();
</script>
</body>
</html>
'''
