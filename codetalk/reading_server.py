"""Core reading room: reuse the guarded review server, with local evidence routes."""
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import console, review
from .config import CACHE_DB_PATH
from .reading_api import commit_record, search_records, write_reading_record
from .review_web import _origin_allowed, create_review_server

log = logging.getLogger(__name__)


def create_reading_server(project_path, cache_path=CACHE_DB_PATH):
    project = Path(project_path).resolve()
    cards, error, _ = review.build_review_cards(project, cache_path=cache_path)
    if error:
        log.warning("Review unavailable; reading workspace remains available")
    server = create_review_server(project, cards or [], cache_path, workspace=True)
    review_handler = server.RequestHandlerClass

    class Handler(review_handler):
        def do_GET(self):
            if not self._guard_host():
                return
            request = urlsplit(self.path)
            query = parse_qs(request.query)
            selected = query.get("project", [None])[0]
            if selected and Path(selected).resolve() != project:
                self._json(403, {"error": "project is fixed for this server"})
                return
            if request.path == "/review":
                if error:
                    self._json(400, {"error": "review unavailable"})
                    return
                self.path = "/"
                super().do_GET()
                return
            try:
                if request.path in {"/", "/console"}:
                    page, _, err = console._build_html(project, True, cache_path=cache_path)
                    if err:
                        self._json(400, {"error": "workspace unavailable"})
                        return
                    body = page.encode("utf-8")
                    self._headers(200, "text/html; charset=utf-8", len(body))
                    self.wfile.write(body)
                elif request.path == "/api/search":
                    self._json(200, search_records(project, query.get("q", [""])[0], cache_path))
                elif request.path.startswith("/api/commit/"):
                    body, status = commit_record(project, request.path[len("/api/commit/"):])
                    self._json(status, body)
                else:
                    self._json(404, {"error": "not found"})
            except Exception:  # noqa: BLE001 - no private exception detail in browser
                log.warning("Reading-room request failed")
                self._json(500, {"error": "workspace unavailable"})

        def do_POST(self):
            request = urlsplit(self.path)
            selected = parse_qs(request.query).get("project", [None])[0]
            if selected and Path(selected).resolve() != project:
                self._json(403, {"error": "project is fixed for this server"})
                return
            self.path = request.path
            if self.path not in {"/capsule", "/reviewed"}:
                super().do_POST()
                return
            if not self._guard_host():
                return
            if not _origin_allowed(self.headers.get("Origin"), self.headers.get("Host"), self.server.server_port):
                self._json(403, {"error": "bad origin"})
                return
            payload = self._read_json()
            if payload is None:
                return
            selected = payload.get("project") if isinstance(payload, dict) else None
            if selected is not None and not isinstance(selected, str):
                self._json(400, {"error": "invalid project"})
                return
            if selected and Path(selected).resolve() != project:
                self._json(403, {"error": "project is fixed for this server"})
                return
            try:
                body, status = write_reading_record(project, self.path, payload, cache_path)
                self._json(status, body)
            except Exception:  # noqa: BLE001 - failed writes must not show success
                log.warning("Reading-room write failed")
                self._json(500, {"error": "record not saved"})

    server.RequestHandlerClass = Handler
    return server
