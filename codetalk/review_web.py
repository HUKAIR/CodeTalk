"""Loopback-only browser review for deterministic decision cards."""
import html
import json
import math
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from .cache import Cache
from .config import CACHE_DB_PATH, redact_data, redact_secrets
from .review_feedback import JUDGMENT_OUTCOMES, build_feedback
from .webserve import inline_json

_CSP = ("default-src 'none'; connect-src 'self'; img-src data:; "
        "script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
_TEMPLATE = Template(
    (Path(__file__).parent / "review.html").read_text(encoding="utf-8"))


def render_review_html(project, cards, judgments):
    payload = {"cards": cards, "judgments": judgments}
    page = _TEMPLATE.substitute(
        project=html.escape(redact_secrets(str(project)), quote=True),
        data=inline_json(redact_data(payload)),
    )
    return redact_secrets(page)


def _host_allowed(raw, port):
    try:
        parsed = urlsplit("//" + (raw or ""))
        return (parsed.hostname in {"127.0.0.1", "localhost"}
                and parsed.port == port and parsed.username is None)
    except ValueError:
        return False


def _origin_allowed(raw, host_raw, port):
    try:
        parsed = urlsplit(raw or "")
        host = urlsplit("//" + (host_raw or ""))
        return (parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost"}
                and parsed.hostname == host.hostname
                and parsed.port == port and parsed.username is None
                and not parsed.path and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _validated_judgment(payload, card_ids):
    if not isinstance(payload, dict):
        return None, 400, "invalid payload"
    card_id = payload.get("card_id")
    if card_id not in card_ids:
        return None, 404, "unknown card"
    status = payload.get("status")
    if status not in JUDGMENT_OUTCOMES:
        return None, 400, "invalid status"
    changed = payload.get("action_changed")
    if status == "confirmed_conflict":
        if not isinstance(changed, bool):
            return None, 400, "action_changed is required"
    elif changed is not None:
        return None, 400, "action_changed only applies to confirmed conflicts"
    elapsed = payload.get("elapsed_seconds", 0)
    if (isinstance(elapsed, bool) or not isinstance(elapsed, (int, float))
            or not math.isfinite(elapsed) or elapsed < 0 or elapsed > 86400):
        return None, 400, "invalid elapsed_seconds"
    return {
        "card_id": card_id, "status": status, "action_changed": changed,
        "elapsed_seconds": round(float(elapsed), 1),
    }, None, None


def create_review_server(project_path, cards, cache_path=CACHE_DB_PATH):
    project = str(Path(project_path).resolve())
    cards_by_id = {card.get("id"): card for card in cards
                   if isinstance(card, dict)
                   and isinstance(card.get("id"), str) and card.get("id")}
    card_ids = set(cards_by_id)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _headers(self, status, content_type, length, disposition=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if disposition:
                self.send_header("Content-Disposition", disposition)
            self.end_headers()

        def _json(self, status, payload, disposition=None):
            body = json.dumps(redact_data(payload), ensure_ascii=False).encode(
                "utf-8", errors="replace")
            self._headers(status, "application/json; charset=utf-8", len(body),
                          disposition)
            self.wfile.write(body)

        def _read_json(self):
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                self._json(415, {"error": "JSON required"})
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 65536:
                    raise ValueError
                return json.loads(self.rfile.read(length))
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json(400, {"error": "invalid JSON"})
                return None

        def _guard_host(self):
            port = self.server.server_address[1]
            if _host_allowed(self.headers.get("Host"), port):
                return True
            self._json(403, {"error": "bad host"})
            return False

        def do_GET(self):
            if not self._guard_host():
                return
            if self.path != "/":
                self._json(404, {"error": "not found"})
                return
            try:
                with Cache(cache_path) as cache:
                    judgments = cache.get_review_judgments(project)
                body = render_review_html(Path(project).name, cards, judgments).encode()
            except Exception:  # noqa: BLE001 - local cache/render errors degrade safely
                self._json(500, {"error": "review unavailable"})
                return
            self._headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)

        def do_POST(self):
            if not self._guard_host():
                return
            port = self.server.server_address[1]
            if not _origin_allowed(
                    self.headers.get("Origin"), self.headers.get("Host"), port):
                self._json(403, {"error": "bad origin"})
                return
            if self.path not in {
                    "/judgment", "/feedback/preview", "/feedback/export"}:
                self._json(404, {"error": "not found"})
                return
            payload = self._read_json()
            if payload is None:
                return
            if self.path != "/judgment":
                self._feedback(payload)
                return
            judgment, status_code, error = _validated_judgment(payload, card_ids)
            if error:
                self._json(status_code, {"error": error})
                return
            try:
                with Cache(cache_path) as cache:
                    cache.put_review_judgment(
                        project, judgment["card_id"], judgment["status"],
                        judgment["action_changed"], judgment["elapsed_seconds"])
                    saved = cache.get_review_judgments(project)[judgment["card_id"]]
            except Exception:  # noqa: BLE001 - persistence errors never expose details
                self._json(500, {"error": "judgment not saved"})
                return
            self._json(200, {"ok": True, "judgment": saved})

        def _feedback(self, payload):
            if not isinstance(payload, dict):
                self._json(400, {"error": "invalid payload"})
                return
            card_id = payload.get("card_id")
            if card_id not in cards_by_id:
                self._json(404, {"error": "unknown card"})
                return
            try:
                with Cache(cache_path) as cache:
                    judgment = cache.get_review_judgments(project).get(card_id)
                if not judgment:
                    self._json(409, {"error": "resolve card before feedback"})
                    return
                feedback = build_feedback(
                    cards_by_id[card_id], judgment,
                    approved_comment=payload.get("approved_comment"))
            except ValueError:
                self._json(400, {"error": "invalid feedback"})
                return
            except Exception:  # noqa: BLE001 - never disclose cache/render details
                self._json(500, {"error": "feedback unavailable"})
                return
            if self.path == "/feedback/preview":
                self._json(200, {"feedback": feedback})
            else:
                self._json(
                    200, feedback,
                    'attachment; filename="codetalk-review-feedback.json"')

    return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def serve_review(project_path, diff_text=None, open_browser=True):
    from .review import build_review_cards
    cards, err, _meta = build_review_cards(project_path, diff_text)
    if err:
        return err
    server = create_review_server(project_path, cards)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"本地决策审查:{url}\n判断只写入本机 cache.db。Ctrl+C 停止。")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return None
