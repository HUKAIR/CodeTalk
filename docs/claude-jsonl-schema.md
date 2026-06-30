# Claude Code Session JSONL — Schema Reference

**Evidence base:** 4 independent sweeps over real local data under `~/.claude/projects/` (CodeTalk, SuperSearch, a large multi-workflow corpus, TradingAgents) plus a targeted edge-case hunt: ~58,000+ JSON lines across ~1,470 files, Claude Code versions **2.1.143 – 2.1.170**, **0 JSON parse failures observed**. Every claim below is empirical; disagreements between sweeps are flagged inline with ⚠️.

---

## 0. File layout (context for everything below)

```
<projects>/<munged-cwd>/
  <sessionId>.jsonl                                  # main session transcript (filename stem == sessionId)
  <sessionId>/subagents/agent-<agentId>.jsonl        # subagent transcript (isSidechain:true)
  <sessionId>/subagents/agent-<agentId>.meta.json    # sidecar: {agentType, description}
  <sessionId>/subagents/workflows/wf_*/agent-<agentId>.jsonl
  <sessionId>/subagents/workflows/wf_*/journal.jsonl # 'started'/'result' records only — different schema family
```

- Subagent files **reuse the parent's `sessionId`** (verified 36k/36k); the filename stem matches `agentId` (17 lowercase hex chars), never `sessionId`. **Group by `sessionId` field, not filename.**
- `isSidechain` is `false` for every main-file record and `true` for every subagent-file record (location and flag are redundant signals; no inline sidechains were ever observed).
- Files **grow while being read** — counts changed between consecutive scans. Snapshot or tolerate partial trailing lines.

---

## 1. Record types: guaranteed vs optional top-level keys

15 distinct `type` values observed. **Zero `type:"summary"` records exist anywhere in this corpus** (0/58k+ lines, all versions 2.1.143–2.1.170) — its documented role (`leafUuid` pointer) is filled by `last-prompt`.

### 1.1 Conversation-envelope types

These four types share a common envelope and participate in the `uuid`/`parentUuid` chain.

**Common envelope — guaranteed on `user`, `assistant`, `attachment`, `system`:**

| Key | Type | Notes |
|---|---|---|
| `type` | str | record discriminator |
| `uuid` | str | UUIDv4 (lowercase 8-4-4-4-12), unique per record |
| `parentUuid` | str\|null | links to a `uuid` **in the same file**; 0 dangling refs observed across all corpora; null at chain roots (root may be an `attachment`, not a user message) |
| `timestamp` | str | strict `YYYY-MM-DDTHH:MM:SS.mmmZ` — 100% regex match, no other format ever seen |
| `sessionId` | str | parent session UUID (see §0) |
| `cwd` | str | absolute path; **can change mid-session** (8 distinct values in one session, incl. `/private/tmp/...` workflow dirs) |
| `gitBranch` | str | `'HEAD'`, `'main'`, feature names; `'HEAD'` = detached/non-repo placeholder; can change mid-file |
| `version` | str | CC version; **changes mid-file across resumes** |
| `isSidechain` | bool | see §0 |
| `userType` | str | always `'external'` |
| `entrypoint` | str | always `'cli'` in this corpus |

**`type: "assistant"`**

| Guaranteed (in addition to envelope) | Optional |
|---|---|
| `message` (full API message object, see §2), `requestId` ⚠️ | `slug`, `agentId` (subagent files only), `attributionAgent`, `attributionPlugin`, `attributionSkill`, `isApiErrorMessage`, `error`, `apiErrorStatus` |

- ⚠️ **Disagreement:** three sweeps found `requestId` on 100% of assistant records; the largest sweep found it **missing on 2/24,079** — both synthetic API-error records. Treat as guaranteed *except* when `isApiErrorMessage:true`.
- `requestId` format `req_011C...` (~28 chars); shared by all JSONL lines of one API message.
- Synthetic error records: `isApiErrorMessage:true`, `error` (e.g. `'rate_limit'`), `apiErrorStatus` (e.g. `'429'`), `message.model = '<synthetic>'`, null usage subfields.
- **CRITICAL — streaming split:** each line holds exactly one content block; one API message spans N consecutive lines sharing `message.id` + `requestId` (up to 7 lines/id observed), each line **repeating the identical `usage` object**.

**`type: "user"`**

| Guaranteed (in addition to envelope) | Optional |
|---|---|
| `message` (`{role:'user', content}` — exactly these two keys), `promptId` ⚠️ | `slug`, `agentId`, `sourceToolAssistantUUID`, `sourceToolUseID`, `toolUseResult`, `isMeta`, `permissionMode` (`auto`/`plan`/`default`), `promptSource` (`typed`/`system`), `origin` (dict with key `kind`), `isCompactSummary`, `isVisibleInTranscriptOnly`, `interruptedMessageId` |

- ⚠️ **Disagreement:** three sweeps found `promptId` on 100% of user records; the largest found it missing on **3/14,581**. Use `.get()`.
- `promptId` is a UUID grouping all records of one human turn; tool_result carriers inherit the originating prompt's id.
- `sourceToolAssistantUUID` = uuid of the assistant record that issued the matching `tool_use` (correct 1,505/1,507 and 30/30 where verified; the 2 misses were interrupted turns).
- `isMeta` on user records: serialized **only when true** (injected /init prompts, skill expansions, caveats — not human input).
- The majority of user records (70–88% depending on corpus) are **tool_result carriers, not human prompts**.

**`type: "attachment"`** — harness-injected context, not API messages, but full envelope + chain membership (a main file's chain root is often an attachment).

| Guaranteed | Optional |
|---|---|
| envelope + `attachment` (payload object with its own `.type`) | `slug`, `agentId` |

`attachment.type` is an **open set**; 20 values observed: `skill_listing`, `deferred_tools_delta`, `task_reminder`, `queued_command` (`prompt`/`commandMode`), `plan_mode`, `plan_mode_exit` (`planFilePath`), `plan_mode_reentry`, `command_permissions`, `hook_success` (`stdout`/`stderr`/`exitCode`/`durationMs`/`hookName`/`hookEvent`/`toolUseID`), `hook_additional_context`, `ultra_effort_enter`, `auto_mode`, `auto_mode_exit`, `file` (`content`/`displayPath`/`filename`), `edited_text_file` (`filename`/`snippet`), `date_change`, `compact_file_reference`, `plan_file_reference`, `invoked_skills`, `already_read_file`.

**`type: "system"`** — no `message` field; payload in flat keys.

| Guaranteed | Optional (subtype-dependent) |
|---|---|
| envelope + `subtype`, `isMeta` (always present, **always false** on system) | `slug`, `content` (str), `durationMs`+`messageCount` (turn_duration), `level` (`info`/`notice`/`warning`), `compactMetadata`+`logicalParentUuid` (compact_boundary), `error`/`retryInMs`/`retryAttempt`/`maxRetries` (api_error), `pendingWorkflowCount`, `pendingBackgroundAgentCount`, `url` |

`subtype` values observed: `turn_duration`, `local_command`, `away_summary`, `compact_boundary`, `informational`, `bridge_status`, `api_error`. 12 distinct key sets exist — treat all non-guaranteed keys as optional.

`compactMetadata` = `{trigger, preTokens, postTokens, durationMs, preCompactDiscoveredTools, preservedSegment{anchorUuid,headUuid,tailUuid}, preservedMessages{allUuids,anchorUuid,uuids}}`.

### 1.2 Sidecar state types (no `uuid`, no `parentUuid`, mostly no `timestamp`)

Emitted ~once per turn; **latest-wins key-value state, not events**. All have `sessionId` except `file-history-snapshot`.

| Type | Exact keys | Notes |
|---|---|---|
| `last-prompt` | `type`, `sessionId`, `leafUuid`; `lastPrompt` **optional** (missing on ~1–3% of records) | `leafUuid` always resolves to an in-file record uuid (874/874 verified) — the transcript-head pointer that `summary` records provide in other corpora. `lastPrompt` may be truncated (201-char copies observed). |
| `mode` | `type`, `sessionId`, `mode` | only value seen: `'normal'` |
| `permission-mode` | `type`, `sessionId`, `permissionMode` | values: `default`, `auto`, `plan` |
| `ai-title` | `type`, `sessionId`, `aiTitle` | auto-generated title, rewritten repeatedly |
| `agent-name` | `type`, `sessionId`, `agentName` | slug-style label; main files only |
| `bridge-session` | `type`, `sessionId`, `bridgeSessionId`, `lastSequenceNum` | |
| `pr-link` | `type`, `sessionId`, `prNumber`, `prRepository`, `prUrl`, `timestamp` | **has** timestamp; anchors PRs |
| `queue-operation` | `type`, `sessionId`, `operation`, `timestamp`; `content` optional | **has** timestamp; `operation`: `enqueue` (with `content`), `dequeue`, `remove`, `popAll` |
| `file-history-snapshot` | `type`, `messageId`, `snapshot`, `isSnapshotUpdate` | **No `sessionId`/`uuid`/`timestamp` at top level.** `snapshot` = `{messageId, timestamp, trackedFileBackups}`; `trackedFileBackups`: file path → `{backupFileName, backupTime, version}` (0–146 entries). `messageId` matches a user record's `uuid`. ⚠️ One sweep reported repo-relative path keys; two reported absolute paths — treat keys as paths of unknown relativity. |

### 1.3 `journal.jsonl` types (different schema family — skip when parsing transcripts)

| Type | Keys | Notes |
|---|---|---|
| `started` | `type`, `key`, `agentId` | `key` = `'v2:<64-hex>'` workflow step cache key |
| `result` | `type`, `key`, `agentId`, `result` | `result` is a dict (the step's StructuredOutput payload, arbitrary schema) ~97% of the time, a plain string otherwise. `started` without matching `result` = step never completed (32 cases observed). |

---

## 2. `message.content` block taxonomy

### 2.1 User messages (`message` = `{role:'user', content}` — never any other key)

`content` is a **string OR an array** (string in ~5–25% of user records depending on corpus).

**String content variants:**
- Plain prose — the genuine human prompt (only ~7–12% of user records overall). May be non-ASCII/UTF-8.
- Synthetic XML-tagged strings: starts with `<command-name>`, `<command-message>`, `<local-command-stdout>`, `<local-command-caveat>`, `<task-notification>`.
- `Stop hook feedback:` prefixed strings.
- `isMeta:true` injected strings.
- `isCompactSummary:true` continuation summaries (12–18 KB, begin `"This session is being continued from a previous conversation"`).
- In subagent files: orchestrator-written task briefs (string content but **not** human words).

**Array content blocks** (homogeneous per record in practice):

| Block type | Exact fields | Notes |
|---|---|---|
| `tool_result` | `type`, `tool_use_id` (`toolu_01...`), `content`; `is_error` **optional** | the dominant case; always the sole element when present. `is_error` absent on ~80% of results — **absence means success**; when present it can be explicitly `false` or `true`. |
| `text` | `type`, `text` | isMeta skill expansions (up to 570 KB) and `'[Request interrupted by user]'` markers |
| `image` | `type`, `source: {type:'base64', media_type:'image/jpeg', data}` | up to 20 per message; lines to 4.4 MB |
| `document` | (PDF attachment) | observed once |

**`tool_result.content` itself is polymorphic:** plain string (~92%); list of `{type:'text', text}`; list of `{type:'tool_reference', tool_name}` (undocumented block type, from ToolSearch); list of image blocks (screenshots).

### 2.2 Assistant messages

`message` keys — **guaranteed:** `id` (`msg_01...`), `type:'message'`, `role:'assistant'`, `model`, `content` (always an array), `stop_reason`, `stop_sequence`, `stop_details`, `usage`. **Near-guaranteed:** `diagnostics` (~99.9%; null or `{cache_miss_reason}`). **Rare:** `container`, `context_management`.

- `stop_reason`: `'tool_use'` | `'end_turn'` | `'stop_sequence'` | `null` (null = intermediate streamed line of a split message).
- `stop_sequence`/`stop_details`: always null where observed.
- `model` values seen: `claude-opus-4-6/-7/-8`, `claude-haiku-4-5-20251001`, `claude-fable-5`, `'<synthetic>'` (error placeholder).
- **One content block per JSONL line**; reassemble by `message.id`.

**Assistant content blocks:**

| Block type | Exact fields |
|---|---|
| `text` | `type`, `text` |
| `thinking` | `type`, `thinking`, `signature` |
| `tool_use` | `type`, `id` (`toolu_01...`), `name`, `input`; ⚠️ `caller` (`{type:'direct'}`) present in 2 of 4 corpora — treat as optional/version-dependent |

Zero `redacted_thinking`, zero image blocks on the assistant side observed.

### 2.3 Tool inputs (observed, with guaranteed input keys)

| Tool | Guaranteed input keys | Optional input keys |
|---|---|---|
| `Bash` | `command` | `description`, `timeout`, `run_in_background`, `dangerouslyDisableSandbox` |
| `Read` | `file_path` (absolute) | `limit`, `offset` |
| `Edit` | `file_path`, `old_string`, `new_string`, `replace_all` | |
| `Write` | `file_path`, `content` | |
| `ExitPlanMode` | `planFilePath` | |
| `WebFetch` | `url` | `prompt` |
| `WebSearch` | `query` | |
| `Skill` | `skill` | `args` |
| `Workflow` | `scriptPath` **or** `script`+`args` | |
| `StructuredOutput` | caller-defined free schema | |

Also seen: `ToolSearch`, `TaskCreate`/`TaskUpdate`, `AskUserQuestion`, `Agent`, `SendUserFile`, `EnterPlanMode`. **A hallucinated lowercase `bash` tool name appeared (both calls errored)** — never match tool names case-sensitively or assume validity.

### 2.4 Top-level `toolUseResult` (sibling of `message` on tool_result-carrier user records)

The structured, machine-readable result. Shapes by originating tool:

- **Bash:** `{stdout, stderr, interrupted, isImage, noOutputExpected}` + optional `returnCodeInterpretation`, `gitOperation`, `dangerouslyDisableSandbox`, `backgroundTaskId`, `persistedOutputPath`. No numeric exit-code field exists. stdout/stderr live **here**, not in the content block.
- **Read:** `{type:'text', file:{filePath, content, numLines, startLine, totalLines}}` (image reads add base64/dimensions/originalSize).
- **Edit:** `{filePath, oldString, newString, replaceAll, originalFile, structuredPatch, userModified}`.
- **Write:** `{type:'create'|'update', filePath, content, originalFile, structuredPatch, userModified}` — `create` vs `update` distinguishes new files.
- `structuredPatch` = list of hunks `{oldStart, oldLines, newStart, newLines, lines}`.
- **Agent:** `{agentId, agentType, prompt, totalDurationMs, totalTokens, totalToolUseCount, usage, toolStats, ...}`; **Workflow:** `{runId, scriptPath, status, summary, taskId, transcriptDir, ...}`; **WebFetch:** `{bytes, code, codeText, result, durationMs, url}`; **WebSearch:** `{query, results, durationSeconds, searchCount}`; **Skill:** `{commandName, success[, allowedTools]}`; **ExitPlanMode:** `{filePath, isAgent, plan}`; **Task tools:** `{taskId, success, updatedFields, statusChange, task}`.
- **On failure, `toolUseResult` degrades to a plain string** (`'Error: ...'`, `'User rejected tool use'`, `'InputValidationError: ...'`, permission denials), correlating with `is_error:true`.
- **Presence rule:** ~100% of tool_result carriers in main session files; almost always **absent** in subagent/workflow files (0/17, 6/321, 200/10,490, 6/85 across corpora). Parsers must fall back to `tool_result.content`.

---

## 3. Minimal field set for the codetalk parser

**File discovery:** recurse `<projects>/<slug>/*.jsonl` plus `<sessionId>/subagents/**/agent-*.jsonl`; skip `journal.jsonl` and `*.meta.json`.

**Per line:** `json.loads` in try/except (skip failures — live files can have partial trailing lines); switch on `obj['type']`; ignore unknown types.

| Need | Where | Extraction rule |
|---|---|---|
| **session_id** | top-level `sessionId` | NOT the filename for subagent files. `isSidechain`/`agentId` mark subagent work (down-weight: their "user" messages are orchestrator briefs). Session label: last `ai-title.aiTitle`; fallback `last-prompt.lastPrompt`. |
| **timestamps** | top-level `timestamp` | Format is exactly `YYYY-MM-DDTHH:MM:SS.mmmZ` (UTC, ms). Parse: `datetime.fromisoformat(ts)` on py≥3.11, else `ts.replace('Z','+00:00')`. Present on every `user`/`assistant`/`attachment`/`system` record + `pr-link`/`queue-operation`; **absent** on all other sidecar types. For repo attribution use `cwd` + `gitBranch` (tolerate `'HEAD'` and mid-session changes); `pr-link` records anchor PRs directly. |
| **user prompt text** | `type=='user'` → `message.content` | Accept iff: content is a **string**, AND `not obj.get('isMeta')`, AND `not obj.get('isCompactSummary')`, AND not `content.startswith('<')` (covers `<command-name>`, `<local-command-stdout>`, `<local-command-caveat>`, `<task-notification>`, `<command-message>`), AND not `content.startswith('Stop hook feedback:')`, AND `not obj.get('isSidechain')`. Also accept list content whose blocks are `type=='text'` (non-meta), filtering `'[Request interrupted'` markers. Skip any record whose list contains a `tool_result`. Keep: `message.content`, `timestamp`, `uuid`, `promptId`, `sessionId`, `cwd`. |
| **assistant text** | `type=='assistant'` → `message.content[]` | Take `block.text` where `block.type=='text'` (optionally `block.thinking` where `'thinking'`). Skip `isApiErrorMessage` records. **Group/merge by `message.id`** to reassemble streamed splits; file order is reliable for ordering. Keep: `message.id`, `message.model`, `timestamp`, `uuid`, `parentUuid`. |
| **tool_use file paths** | assistant `tool_use` blocks | Writes: `Edit`/`Write` (`NotebookEdit` expected, unobserved) → `input.file_path`. Reads: `Read` → `input.file_path`. Plans: `ExitPlanMode` → `input.planFilePath`. `Bash` → parse `input.command` heuristically (`input.description` helps). Confirm success by joining `tool_use.id` → next user record's `tool_result.tool_use_id` (or via `sourceToolAssistantUUID`): failure iff `is_error is True` or `toolUseResult` is a string. Prefer `toolUseResult.filePath`/`.structuredPatch`/`.type('create'/'update')` when present, but **never require `toolUseResult`** (absent in subagent files). Bonus signal: `file-history-snapshot.snapshot.trackedFileBackups` keys = files actually modified. |
| **token usage** | `message.usage` on assistant only | Guaranteed: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, `cache_creation{ephemeral_1h_input_tokens, ephemeral_5m_input_tokens}`, `service_tier`, `inference_geo` (any can be null on synthetic records). Optional: `server_tool_use{web_search_requests, web_fetch_requests}`, `speed`, `iterations` (list of per-iteration usage dicts). **MUST dedupe by `message.id` before summing** — usage is repeated on every line of a split message (naive summing inflates ~2.5–2.9×). Subagent aggregate usage also appears in `Agent` `toolUseResult.usage`. |

---

## 4. Tolerance rules — deviation → required degradation

| # | Deviation | Observed frequency | Degradation |
|---|---|---|---|
| 1 | Line fails `json.loads` / blank line | 0 in 58k+ lines — but files **grow live** and trailing lines can be partial | try/except per line; skip and count; re-scan tolerant of changed counts |
| 2 | Huge lines | max **4,386,639 bytes** (20 base64 JPEGs in one user record); 565 KB isMeta text; 35 lines >1 MB | never use fixed line buffers; budget ≥5 MB/line; skip image-block payloads |
| 3 | `message` absent | all 11 non-conversation types | switch on `type` first; only touch `message` for `user`/`assistant` |
| 4 | `message.content` string vs array | string on ~4% of all messaged records (user only) | branch on `isinstance(content, str)` |
| 5 | Assistant message split across lines | up to 7 lines per `message.id`; `stop_reason` null on intermediates | merge text and dedupe usage by `message.id` |
| 6 | `uuid`/`timestamp`/`sessionId` absent | all sidecar types lack uuid+timestamp; `file-history-snapshot` lacks even `sessionId` | use `.get()` for every metadata read; never key generic logic on these fields |
| 7 | `type:"summary"` absent | 0 occurrences in 2.1.143–2.1.170 | use `last-prompt.leafUuid` as head pointer and `ai-title` for labels; still accept `summary` if encountered (legacy/other corpora) |
| 8 | Unknown record types / attachment subtypes / system subtypes | open sets; 15 types today | ignore unknown `type`; ignore unknown `attachment.type`/`subtype` |
| 9 | `isMeta` | serialized only-when-true on user; always-present-false on system | `obj.get('isMeta')` truthy check; exclude truthy from user-intent |
| 10 | Sidechain records | entire subagent files (`isSidechain:true`); never inline | exclude sidechain user strings from human intent; fold assistant/tool activity into parent session via `sessionId` |
| 11 | Compaction | `isCompactSummary:true` user records (12–18 KB machine summaries) + `isVisibleInTranscriptOnly` + system `compact_boundary` (`compactMetadata`, `logicalParentUuid`) + `compact_file_reference` attachments | exclude from user intent; optionally record "session was compacted" |
| 12 | Synthetic API-error assistant records | 21+1 observed: `isApiErrorMessage:true`, `model:'<synthetic>'`, null usage subfields, `requestId` may be missing | skip for text/usage; guard all `usage` subfield reads against null |
| 13 | `tool_result.is_error` absent | ~80% of results | absence == success; presence may be explicit `false` |
| 14 | `toolUseResult` absent / string / dict | absent in ~98% of subagent-file results; string on errors | three-way branch: dict → structured; str → failure; absent → fall back to `tool_result.content` |
| 15 | `tool_result.content` polymorphic | str (~92%), list of text / `tool_reference` / image blocks | accept str or list; handle unknown block types (e.g. `tool_reference`) by skipping |
| 16 | Tool names | hallucinated `bash` (lowercase, errored); open set | never whitelist case-sensitively; never assume success without checking the result |
| 17 | `parentUuid` null / chain roots | roots can be attachments, not user messages; subagent files root independently | treat null as root; don't assume line 1 is the root; in-file resolution is reliable (0 dangling) |
| 18 | Metadata drift mid-file | `cwd` (8 values in one session), `gitBranch`, `version` all change across resumes | read per-record, never cache per-file |
| 19 | `gitBranch == 'HEAD'` | majority of records in some corpora | treat as "unknown branch", not a literal name |
| 20 | Sidecar state repetition | `ai-title`/`last-prompt`/`mode`/`permission-mode`/`agent-name`/`bridge-session` ~once per turn | latest-wins; never treat as events |
| 21 | `lastPrompt` missing on `last-prompt`; truncated values (201 chars) | ~1–3% missing | `.get()`; treat as truncatable preview, not canonical text |
| 22 | Non-ASCII prompts | Chinese prompts observed | decode UTF-8 throughout |
| 23 | `journal.jsonl` in transcript dirs | `{started, result}` schema family, no uuid/timestamp | exclude by filename |
| 24 | `promptId`/`requestId` missing | 3/14,581 user; 2/24,079 assistant | `.get()` even on "guaranteed" keys |

---

## 5. Open uncertainties

1. **`type:"summary"` records** — documented and reportedly seen in other corpora, but absent in every file here (2.1.143–2.1.170). Their exact shape (and whether `leafUuid` semantics match `last-prompt`) is unverified; the parser should accept both.
2. **`file-history-snapshot.trackedFileBackups` key paths** — one sweep reported repo-relative keys (`'CLAUDE.md'`), two reported absolute paths. Possibly version- or cwd-dependent. Treat keys as paths of unknown relativity; resolve against `cwd` if not absolute.
3. **`caller` field on `tool_use` blocks** (`{type:'direct'}`) — present in 2 of 4 corpora (versions 2.1.143 and 2.1.170), unreported in the middle versions. Unknown whether it was absent or just unrecorded; only value seen is `'direct'` (other values, e.g. for MCP/agent callers, unobserved).
4. **`NotebookEdit` input keys** — tool never observed; `notebook_path` is assumed from API docs, not confirmed.
5. **Bash exit codes** — no numeric exit-code field exists anywhere in `toolUseResult` (only a sometimes-present `returnCodeInterpretation` string); exact failure semantics beyond `is_error` are unconfirmed.
6. **`entrypoint` and `userType`** — only `'cli'` and `'external'` ever observed; values from other entry points (IDE, SDK, web bridge) are unknown and may change envelope guarantees.
7. **`mode` record values** — only `'normal'` observed; the value space is unknown.
8. **`stop_details` structure** — always null; its populated shape is unknown.
9. **`inference_geo` semantics** — values `'not_available'`, empty string, and null all observed; meaning unconfirmed.
10. **`queue-operation` `popAll`** — observed once; payload semantics unconfirmed.
11. **Inline sidechains** — `isSidechain:true` was only ever seen in separate `agent-*.jsonl` files; whether any CC version writes sidechain records inline in the main file is unconfirmed (the flag should still be checked per-record, not per-file).
12. **`origin` field** — dict with key `kind` on rare user records; value space unobserved beyond existence.
13. **`started`/`result` `key` hash** — `'v2:<sha256>'` is presumed a workflow step cache key; the hashed material is unconfirmed.
14. **Cross-version drift** — corpus spans 2.1.143–2.1.170 only; older formats (e.g. pre-`last-prompt`, inline summaries, different timestamp precision) and future additions are uncovered. The two `sourceToolAssistantUUID` mismatches (interrupted turns) suggest linkage fields can be stale — always verify joins via `tool_use_id` when both signals exist.
15. **Image/`document` blocks in user content** — observed in only one corpus (48 image messages, 1 document); their full field inventory (e.g. non-JPEG media types, `document` block keys) is incomplete.