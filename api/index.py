from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"


def _read_file(path: Path) -> tuple[bytes, str]:
    data = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
        content_type = f"{content_type}; charset=utf-8"
    return data, content_type


def app(environ, start_response):
    raw_path = environ.get("PATH_INFO", "/") or "/"
    path = unquote(raw_path)

    if path in {"/", ""}:
        file_path = INDEX_FILE
    else:
        candidate = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if not str(candidate).startswith(str(FRONTEND_DIR.resolve())) or not candidate.is_file():
            file_path = INDEX_FILE
        else:
            file_path = candidate

    try:
        body, content_type = _read_file(file_path)
        start_response("200 OK", [("Content-Type", content_type), ("Cache-Control", "public, max-age=3600")])
        return [body]
    except FileNotFoundError:
        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return [b"Not Found"]
