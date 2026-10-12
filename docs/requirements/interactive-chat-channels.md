# Interactive chat recipe + channel fronts

Incubating requirements for channel-agnostic `june.chat` and soft-point
composition with other June recipes (imagegen first).

## Ownership

- **June:** concrete interactive recipe, soft-point fills (model, tools, context,
  media), channel adapters, console viz of the chat lane.
- **MechaHarness:** graph execution / host_kit / checkpoints. Do **not** promote a
  conversational skeleton until a second host wants the same shape.

## Entry contract

All fronts normalize to `ChannelMessage` → `ChatService.handle` →
`run_chat_recipe` (`src/june/recipes/chat/`). No frontend-specific graph logic.

| Front | Adapter | Notes |
|-------|---------|--------|
| Console `/api/chat` | `WebappAdapter` | Mirrors recipe phases onto hub chat lane |
| REST `/v1/chat` | `RestChatAdapter` | Same DTO; no hub mirroring |
| Telegram / Discord | stubs | `NotImplementedError`; `NullPoller` remains |

## Recipe graph

`refine_input` → `context_optimize` → `tool_loop` → `render_reply`

Soft points: Junespark provider, `ToolRegistry`, documents/KG, chat settings.

## Imagegen soft point

Tool `generate_image` binds `run_imagegen_recipe` (oneshot or criteria_refine).
Tool JSON includes `{ "media": { "kind": "image", ... } }`; `render_reply` appends
a `ContentPart`. Prefer DocumentStore ids when available.

Nested recipe compose (HF-03) is deferred; tool bind keeps chat topology linear.

## Promotion bar

Promote a generic MH conversational recipe only after reuse evidence outside June
and a clean split of soft points vs control skeleton. Until then IDs stay
`june.chat.*`.

## Out of scope

Voice pipelines, Switchboard, MCP embedding, live Discord/Telegram bots.
