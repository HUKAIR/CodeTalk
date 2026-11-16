# Reading room: functions and backend map

The B reading room retains the original prototype composition and reuses the
seven-view console and existing review contracts. The seven views live in the
Workspace menu so the reading page keeps its original width. Search opens from
the header or `/`; Reading, Compare and Bookmarks remain in the top navigation.
It introduces no frontend build chain or core dependency. All generated pages
inline their styles and scripts. Original sources and cached interpretation
remain separate.

| Function | `console` static export | `console --serve` | Optional `web` | Data / endpoint |
|---|---|---|---|---|
| Overview, coverage, due capsules | Snapshot | Live on page reload | Live on page reload | `console._assemble`, local cache |
| Commit chapters, original chosen/rejected/watch notes | Included | Included | Included | Git messages, full SHA |
| Original diff / before-and-after lines | Disabled with explanation | Available | Available | `GET /api/commit/{sha}`, bounded to 8,000 characters |
| Local filters and bookmarks | Available | Available | Available | Browser storage, project-specific key; no remote write |
| Full-repository search | Local loaded-record filter only | Available | Available | `GET /api/search?q=…`; original / cached / conversation labels |
| Mark as read | Disabled | Saves locally | Saves locally | `POST /reviewed`; a reading signal, not review approval |
| Capsule answer / change answer | Disabled | Saves locally | Saves locally | `POST /capsule`; validates project ownership |
| Decision graph | Included | Included | Included; full graph also at `/graph` | Existing graph assembly; same-file links are not causation |
| Development thread (`graph`) | Read-only; saved notes are baked in | `/graph`: notes, understood marks, plans, links | Same as local service | `POST /graph/annotation`, `POST /reviewed`; notes live only in the local cache |
| Comprehension debt | Included | Updated on page reload | Updated on page reload | Existing debt and capsule/read records |
| File tree and decision history | Included | Updated on page reload | Updated on page reload | Existing file tree / commit grounding |
| Prompt replay and session recap | Included if present | Available if present | Available if present | Existing session parsers; honest empty state |
| Current-change review | Service required | `/review` | `/review` | Existing Git diff / review cards |
| Four judgments + action-changed flag | Service required | Saves locally | Saves locally | `POST /judgment`; existing validation and cache |
| Feedback preview / JSON export | Service required | Available after judgment | Available after judgment | `POST /feedback/preview`, `/feedback/export`; optional and local |
| Grounded chat / source citations | Hidden | Hidden | Console dock and `/` | `POST /api/chat`, `/api/chat/stream`; selected project in JSON |
| Standalone timeline / course | Existing CLI exports | Existing CLI commands | `/tunnel`, `/course` | Existing renderers; no removed capability |
| Project list / graph JSON | Not applicable | Fixed single project | Available | `GET /api/projects`, `/api/graph` |
| Language, theme, keyboard | Available | Available | Existing controls | EN/中文, light/dark where supported, 1–7 views, `/`, Escape |

The stdlib service binds one project and rejects another `project` selector.
The optional web service retains `?project=…` in links, searches, source requests,
review/feedback and writes. Requests are loopback-only and same-origin guarded.
The core review page is a snapshot of the diff at server start; restart after
editing the working tree. The optional web review page rebuilds cards on load
and refuses judgments for cards no longer present.

`tests/test_reading_room.py` uses actual synthetic Git commits and an isolated
cache to exercise sources, both HTTP adapters, capsule/read/judgment persistence,
all four outcomes, feedback, project selection and hostile-origin rejection.
Desktop acceptance additionally checks navigation, original/diff disclosure,
bookmarks across reload, search, language/theme, keyboard, and browser errors.
The static illustrative `index.html` and gallery simulate interactions; use
[`scripts.demo_reading_room`](demo.md) for real backend persistence.
