"""Inspectable, no-network plan for optional narrative enrichment."""
import json
from urllib.parse import urlsplit

from . import enrich
from .config import SECRET_PATTERN_NAMES, redact_data, redact_secrets_with_counts
from .gitlog import CHARS_PER_TOKEN
from .llm import ANTHROPIC_BASE_URL
from .prompts import NARRATIVE_SCHEMA, SYSTEM_PROMPT

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def endpoint_details(cfg):
    provider = str(cfg.get("provider") or "")
    pconf = (cfg.get("providers") or {}).get(provider) or {}
    base_url = (ANTHROPIC_BASE_URL
                if provider == "anthropic" else str(pconf.get("base_url") or ""))
    base_url = base_url.rstrip("/")
    try:
        parsed = urlsplit(base_url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
        if (parsed.scheme not in {"http", "https"} or not host
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError("HTTP(S) endpoint without credentials required")
        display_host = f"[{host}]" if ":" in host else host
        origin = f"{parsed.scheme}://{display_host}"
        if port is not None:
            origin += f":{port}"
        endpoint = ((origin + "/v1/messages") if provider == "anthropic"
                    else base_url + "/chat/completions")
        return {"origin": origin, "endpoint": endpoint,
                "loopback": host in _LOOPBACK_HOSTS, "error": None}
    except (ValueError, TypeError) as exc:
        return {"origin": "[invalid endpoint]", "endpoint": "[invalid endpoint]",
                "loopback": False, "error": str(exc)}


def _input_texts(commits, project):
    yield enrich._project_context(project)  # noqa: SLF001 - same package contract
    for commit in commits:
        for key in ("author", "subject", "body", "stat", "diff_excerpt"):
            yield str(commit.get(key) or "")
        for match in (commit.get("matches") or [])[:2]:
            session = match.get("session") or {}
            yield str(session.get("title") or "")
            yield from (str(v) for v in (session.get("prompts") or [])[:6])
            yield from (str(v) for v in (session.get("excerpts") or [])[:6])


def _redaction_counts(commits, project):
    totals = {name: 0 for name in SECRET_PATTERN_NAMES}
    for text in _input_texts(commits, project):
        _redacted, counts = redact_secrets_with_counts(text)
        for name, count in counts.items():
            totals[name] += count
    return totals


def build_plan(cfg, commits, pending, project, sources, evidence_backfilled,
               reenrich=False, allow_remote=False, payload_preview=False):
    endpoint = endpoint_details(cfg)
    no_llm = bool(cfg.get("no_llm"))
    if no_llm:
        execution = "disabled_by_no_llm"
    elif payload_preview:
        execution = "preview_only_no_request"
    elif endpoint["loopback"]:
        execution = "loopback_execution"
    elif allow_remote:
        execution = "remote_execution_authorized"
    else:
        execution = "remote_blocked_no_authorization"
    model_request = execution in {
        "loopback_execution", "remote_execution_authorized"} and bool(pending)
    return redact_data({
        "execution": execution,
        "network_egress": execution == "remote_execution_authorized" and bool(pending),
        "model_request": model_request,
        "configured_key_authorizes_remote": False,
        "provider": cfg.get("provider"),
        "destination_origin": endpoint["origin"],
        "destination_endpoint": endpoint["endpoint"],
        "endpoint_error": endpoint["error"],
        "model": cfg.get("model"),
        "scope": {"total_commits": len(commits), "uncached_commits": len(pending),
                  "reenrich": bool(reenrich)},
        "local_sources": ["git_commit_history", "git_diff_excerpt",
                          "project_context", "local_cache_prior_narrative"]
                         + ["session:" + source for source in sources],
        "bounded_input_categories": [
            {"name": "project_context", "cap": "4000 characters per run"},
            {"name": "commit_author", "cap": "200 characters per request"},
            {"name": "commit_subject", "cap": "500 characters per request"},
            {"name": "commit_body", "cap": "500 characters per request"},
            {"name": "diff_stat", "cap": "2000 characters per request"},
            {"name": "diff_excerpt", "cap": str(
                int(cfg.get("diff_token_budget") or 0) * CHARS_PER_TOKEN)
             + " characters per request"},
            {"name": "session_context", "cap":
             "2 matches; 6 prompts x 400 and 6 excerpts x 1000 characters"},
            {"name": "prior_narrative", "cap": "200 characters per request"},
        ],
        "redaction_counts": _redaction_counts(pending, project),
        "potentially_visible_after_redaction": [
            "ordinary_code", "business_logic", "filenames", "author_data",
            "non_secret_conversation_text",
        ],
        "cache_effects": {
            "deterministic_evidence_records_updated": evidence_backfilled,
            "generated_narratives_if_executed": len(pending),
            "existing_sha_narratives": (
                "may be replaced only because --reenrich was explicit"
                if reenrich else "preserved"),
        },
        "provider_retention": (
            "Retention is controlled by the selected provider/runtime and is "
            "outside CodeTalk guarantees."),
    })


def outbound_request_preview(cfg, commit, cache, project):
    endpoint = endpoint_details(cfg)
    outbound = enrich.outbound_inputs(commit, cache, project)
    return redact_data({
        "method": "POST", "destination": endpoint["endpoint"],
        "credentials": "omitted",
        "body": {"model": cfg.get("model"),
                 "system_prompt": SYSTEM_PROMPT,
                 "output_language": cfg.get("output_lang") or "中文",
                 "cache_prefix": outbound["cache_prefix"],
                 "user_prompt": outbound["user_prompt"],
                 "response_schema": NARRATIVE_SCHEMA,
                 "max_output_tokens": 3000},
    })


def render_plan(plan, preview=None):
    payload = {"enrichment_plan": plan}
    if preview is not None:
        payload["outbound_request_preview"] = preview
    return json.dumps(payload, ensure_ascii=False, indent=2)
