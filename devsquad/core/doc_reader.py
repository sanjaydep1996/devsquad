# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Reading attachments that aren't plain text: the text inside PDFs, and what an image shows.

PDF text comes from the page streams with the standard library only. It works for PDFs made by
word processors and browsers, not for scanned pages (those are pictures of text).
Images are described by a local Ollama vision model such as llava, only when one is installed.
"""

import base64
import json
import re
import urllib.error
import urllib.request
import zlib
from typing import Optional

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
MAX_PDF_STREAM = 8 * 1024 * 1024

_STREAM = re.compile(rb"<<(.{0,600}?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.S)
_TEXT_BLOCK = re.compile(rb"BT(.*?)ET", re.S)
_OP = re.compile(rb"(\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|\[(?:\\.|[^\]\\])*\])\s*(Tj|TJ|'|\")|(T\*|Td|TD)(?=\s|$)")
_ESCAPES = {b"n": "\n", b"r": "", b"t": " ", b"b": "", b"f": "", b"(": "(", b")": ")", b"\\": "\\"}


def _literal(raw: bytes) -> str:
    """Decodes a PDF (string) literal, without its parentheses."""
    out, i = [], 0
    while i < len(raw):
        c = raw[i:i + 1]
        if c == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            octal = re.match(rb"[0-7]{1,3}", raw[i + 1:i + 4])
            if octal:
                out.append(chr(int(octal.group(0), 8) % 256))
                i += 1 + len(octal.group(0))
                continue
            i += 2  # line continuation or an unknown escape
            continue
        out.append(raw[i:i + 1].decode("latin-1"))
        i += 1
    return "".join(out)


def _hex(raw: bytes) -> str:
    digits = re.sub(rb"\s", b"", raw)
    if len(digits) % 2:
        digits += b"0"
    data = bytes.fromhex(digits.decode("ascii"))
    if len(data) >= 2 and len(data) % 2 == 0 and data[0] == 0:  # two-byte text, common for UTF-16
        try:
            return data.decode("utf-16-be")
        except UnicodeDecodeError:
            pass
    return data.decode("latin-1")


def _string(token: bytes) -> str:
    if token.startswith(b"("):
        return _literal(token[1:-1])
    if token.startswith(b"<"):
        return _hex(token[1:-1])
    parts = []  # a TJ array: strings with spacing numbers between them
    for m in re.finditer(rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>|-?\d+\.?\d*", token[1:-1]):
        piece = m.group(0)
        if piece[:1] in (b"(", b"<"):
            parts.append(_string(piece))
        elif float(piece) < -200:  # a wide gap is a space between words
            parts.append(" ")
    return "".join(parts)


def pdf_text(data: bytes, limit: int = 200_000) -> str:
    """The text in a PDF's content streams, in page order. Empty when there's none to read."""
    if not data.startswith(b"%PDF"):
        return ""
    lines = []
    for m in _STREAM.finditer(data):
        head, body = m.group(1), m.group(2)
        if len(body) > MAX_PDF_STREAM or re.search(rb"/Subtype\s*/Image|/Type\s*/XObject", head):
            continue
        if b"FlateDecode" in head:
            try:
                body = zlib.decompressobj().decompress(body, MAX_PDF_STREAM)
            except zlib.error:
                continue
        elif b"/Filter" in head:
            continue  # other encodings (images, fonts) carry no readable text
        for block in _TEXT_BLOCK.finditer(body):
            line = []
            for op in _OP.finditer(block.group(1)):
                if op.group(3) or op.group(2) in (b"'", b'"'):
                    if line:
                        lines.append("".join(line))
                        line = []
                if op.group(1):
                    line.append(_string(op.group(1)))
            if line:
                lines.append("".join(line))
        if sum(map(len, lines)) > limit:
            break
    text = "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in lines)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def describe_image(data: bytes, model: str, ollama_url: str = "http://localhost:11434", timeout: float = 120.0) -> Optional[str]:
    """What a local vision model sees in the image, or None when it can't be asked."""
    body = json.dumps({
        "model": model,
        "prompt": ("Describe this image for a software team planning a feature. If it is a screen or mockup, list the "
                   "sections, controls, labels and any text exactly. If it is a diagram, list the parts and how they connect."),
        "images": [base64.b64encode(data).decode("ascii")],
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = json.loads(resp.read().decode("utf-8")).get("response", "")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return text.strip() or None
