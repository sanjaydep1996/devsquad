# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Project files: planning material (briefs, mockups, schemas) that people upload for the team to work from."""

import pathlib
import re
from typing import Any, Callable, Dict, List, Optional

from .doc_reader import IMAGE_SUFFIXES, pdf_text

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 200
# How much of the attached text goes into a prompt. Local models have small context windows.
MAX_CONTEXT_CHARS = 12000

# Files whose contents agents can read as plain text
TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".css", ".sql", ".log",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".c", ".h", ".cpp", ".cs",
    ".sh", ".toml", ".ini", ".env.example", ".graphql", ".proto",
}


class FileRejected(ValueError):
    """The upload can't be stored. The message is safe to show to the person."""


class ProjectFiles:
    """Stores uploads flat in .devsquad/files/, which git ignores."""

    def __init__(self, repo_root: Optional[pathlib.Path] = None):
        self.folder = (repo_root or pathlib.Path.cwd()).resolve() / ".devsquad" / "files"

    @staticmethod
    def safe_name(name: str) -> str:
        """A plain file name with no folders, so nothing can be written outside the files folder."""
        base = re.split(r"[\\/]", name or "")[-1].strip()
        hidden = base.startswith(".")
        base = re.sub(r"[^A-Za-z0-9._ ()\-]+", "_", base).strip(" .")[:120]
        if not base or hidden:
            raise FileRejected("That file name can't be used. Rename the file and try again.")
        return base

    def path(self, name: str) -> pathlib.Path:
        return self.folder / self.safe_name(name)

    def _info(self, p: pathlib.Path) -> Dict[str, Any]:
        st = p.stat()
        return {"name": p.name, "size": st.st_size, "modified": st.st_mtime, "readable": p.suffix.lower() in TEXT_SUFFIXES or p.suffix.lower() == ".pdf",
                "image": p.suffix.lower() in IMAGE_SUFFIXES}

    def save(self, name: str, data: bytes) -> Dict[str, Any]:
        if len(data) > MAX_FILE_BYTES:
            raise FileRejected(f"That file is over the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")
        target = self.path(name)
        self.folder.mkdir(parents=True, exist_ok=True)
        if not target.exists() and len(self.list()) >= MAX_FILES:
            raise FileRejected(f"There are already {MAX_FILES} files. Delete some first.")
        target.write_bytes(data)
        return self._info(target)

    def list(self) -> List[Dict[str, Any]]:
        if not self.folder.is_dir():
            return []
        files = [self._info(p) for p in self.folder.iterdir() if p.is_file() and not p.name.startswith(".")]
        return sorted(files, key=lambda f: f["modified"], reverse=True)

    def read(self, name: str) -> Optional[bytes]:
        try:
            p = self.path(name)
        except FileRejected:
            return None
        return p.read_bytes() if p.is_file() else None

    def delete(self, name: str) -> bool:
        try:
            p = self.path(name)
        except FileRejected:
            return False
        if not p.is_file():
            return False
        p.unlink()
        return True

    def context_for(self, names: List[str], describe_image: Optional[Callable[[bytes], Optional[str]]] = None) -> str:
        """What the agents are told about attached files.

        Text files go in as they are and PDFs as their extracted text. Images are described by
        `describe_image` (a local vision model) when one is given; otherwise they're listed by name.
        """
        readable, unreadable = [], []
        budget = MAX_CONTEXT_CHARS
        for name in names or []:
            data = self.read(str(name))
            if data is None:
                continue
            safe = self.safe_name(str(name))
            suffix = pathlib.Path(safe).suffix.lower()
            text, label = None, safe
            if suffix in TEXT_SUFFIXES:
                text = data.decode("utf-8", errors="replace")
            elif suffix == ".pdf":
                text = pdf_text(data) or None
                label = f"{safe} (text from the PDF)"
            elif suffix in IMAGE_SUFFIXES and describe_image is not None and budget > 0:
                text = describe_image(data)
                label = f"{safe} (described by a vision model)"
            if text is None or budget <= 0:
                unreadable.append(safe)
                continue
            if len(text) > budget:
                text = text[:budget] + "\n[cut short]"
            budget -= len(text)
            readable.append(f"--- {label} ---\n{text}")
        if not readable and not unreadable:
            return ""
        parts = ["REFERENCE FILES FROM THE USER:"] + readable
        if unreadable:
            parts.append("Also attached, but their contents couldn't be read (scanned PDFs, images without a vision model, "
                         "or over the length limit): " + ", ".join(unreadable))
        return "\n\n".join(parts)
