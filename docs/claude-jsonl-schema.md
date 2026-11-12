# Claude Code Session JSONL — Parser Compatibility Notes

These notes describe record shapes relevant to the local parser. They are not an
upstream schema guarantee. Producers can add fields, omit fields, or change shapes;
use defensive reads and preserve uncertainty.

This public reference contains no transcript excerpts, real session identifiers,
local usernames, private repository names, or statistics from a person's usage.
Examples below are synthetic. Consult the parser and its tests for implemented
behavior; the field catalogue is not a promise that every field is consumed.

## File layout

```text
<projects>/<project-slug>/
  <session-id>.jsonl
  <session-id>/subagents/agent-<agent-id>.jsonl
  <session-id>/subagents/agent-<agent-id>.meta.json
  <session-id>/subagents/workflows/<workflow>/agent-<agent-id>.jsonl
  <session-id>/subagents/workflows/<workflow>/journal.jsonl
```

Subagent filenames can identify an agent while the `sessionId` field identifies
its parent session. Do not treat every subagent file as a separate human session.
Files can grow while being read; tolerate incomplete trailing lines. Metadata
sidecars and workflow journals are not ordinary conversation transcripts.

## Conversation records

| Field | Expected use | Handling |
| --- | --- | --- |
| `type` | Record discriminator | Ignore unknown types without failing the file |
| `uuid`, `parentUuid` | Record identity and links | Optional; a parent can be null or unavailable |
| `sessionId` | Session grouping | Prefer explicit identity to a filename guess |
| `timestamp` | Event time | Parse cautiously; missing or invalid values are not current time |
| `cwd`, `gitBranch` | Repository context | May change within a file; `HEAD` need not name a branch |
| `version` | Producer version | Informational, not proof of a fixed schema |
| `isSidechain` | Subagent activity | Distinguish generated task briefs from human prompts |
| `message` | User or assistant payload | May be absent on non-conversation records |

A user message may contain plain text or a list of blocks. A list may carry tool
results, images, text, or future block types. Do not stringify arbitrary blocks
and present them as a user's words.

An assistant message may contain `text`, `thinking`, or `tool_use` blocks. One
message can be split across multiple JSONL records with the same `message.id`.
Repeated usage metadata must not be summed once per fragment.

### Synthetic example

```json
{
  "type": "user",
  "sessionId": "example-session",
  "timestamp": "2000-01-01T00:00:00.000Z",
  "message": {"role": "user", "content": "Explain the synthetic example."}
}
```

The identifiers and timestamp above are placeholders, not captured user data.

## User intent versus injected content

The following are signals that content is not an ordinary human prompt:

- `isMeta` or `isCompactSummary` is true.
- The record is a subagent brief marked with `isSidechain`.
- Content contains a `tool_result` block.
- Text is a command wrapper, task notification, local command output, interruption
  marker, or hook feedback.

Read flags with `.get()` and handle absent or malformed content. Do not treat
compaction summaries or agent-generated task instructions as verbatim user intent.

## Tool actions and results

A `tool_use` block can include `id`, `name`, and `input`. File-oriented tools can
carry paths in keys such as `file_path`, `filePath`, or `planFilePath`; shell inputs
need separate parsing. A recorded tool request alone does not prove that a write
succeeded or that the requested task was completed.

Results can be represented by a `tool_result` block, a top-level `toolUseResult`,
or both. `toolUseResult` can be an object, a failure string, or absent. Match a
result through its tool-use identifier when possible. Check explicit error flags
and avoid treating missing structured output as a successful action by default.

Possible structured fields include `stdout`, `stderr`, `filePath`,
`structuredPatch`, `interrupted`, and `type`. These are examples of shapes to
handle, not a required field set. Unknown tool names and result forms should
produce a bounded fallback rather than a parser crash.

## Sidecar and workflow records

| Record family | Typical role | Handling |
| --- | --- | --- |
| `ai-title`, `last-prompt`, `agent-name` | Session display state | May repeat; labels are not canonical intent |
| `mode`, `permission-mode` | Producer state | Values are open-ended |
| `pr-link` | Pull-request reference | Treat links and repository names as user data |
| `queue-operation` | Queue events | Do not turn queued work into completed work |
| `file-history-snapshot` | File backup metadata | Paths and identity fields may differ from conversation records |
| `started`, `result` in `journal.jsonl` | Workflow execution records | Keep separate from transcript message parsing |

A legacy `summary` record and a newer `last-prompt` record need not have identical
semantics. Avoid assuming every producer emits either one.

## Tolerance and privacy

- Catch per-record JSON and shape failures; continue with an explicit limitation.
- Accept Unicode text; avoid fixed assumptions about message length or block count.
- Use bounded extraction and skip embedded image/document payloads when collecting
  textual evidence.
- Handle null, absent, or malformed timestamps, identifiers, and usage fields.
- Resolve relative paths against the applicable record context; do not infer a
  stable repository from the first line alone.
- Keep local paths, transcript text, request identifiers, prompts, and tool output
  out of public fixtures and documentation.
- Use synthetic fixtures for regressions. Redaction is a safeguard, not proof that
  arbitrary real session data is suitable for publication.

## Uncertainties

Formats vary across producer versions, entry points, and failure modes. Unknown
record types, changed tool schemas, incomplete links, and partial files remain
possible. The parser must not turn these gaps into claims of complete evidence,
user intent, successful execution, or task completion.
