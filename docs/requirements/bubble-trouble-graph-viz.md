# Bubble Trouble × MechaHarness graph visualization

## Why this console exists

The console’s job is **realtime visual feedback on the live execution graph**.

MechaHarness graphs are not a single cursor marching down a list. They can have
**multiple active loci at once** (fan-out branches, nested tool recipes, stacked
cron/chat instances) and progress in **non-linear** ways (retry, nest dive,
parallel then join). A linear event log forces humans to reconstruct that
topology in their head. A spatial graph *is* the topology — status washes over
nodes and edges as the machine moves — so concurrency and branching are
intuitive rather than archaeological.

Beauty (Bubble Trouble) is in service of that utility: make the live frontier
obvious, keep finished structure readable, and never invent a second
observability graph. Topology and status come from MH checkpoints + tapped
events only (HF-05).

MechaHarness `recipes render` is the **structural** reference (what belongs
where). Bubble Trouble is the **aesthetic** we expand — not a flat SVG clone.

## Ownership

- **June:** live continuous-zoom world (`world.py` + `graph.js`), multi-locus
  execution lighting, stacks/bands, inspector, Bubble Trouble chrome.
- **MechaHarness:** `NodeComponent` kinds, checkpoint nest, edge reasons,
  `recipes render` layout semantics (inspiration only — do not embed MH SVG).

Cross-links: [`mechaharness-dynamic-tool-graph.md`](./mechaharness-dynamic-tool-graph.md),
[`interactive-chat-channels.md`](./interactive-chat-channels.md),
[`mechaharness-host-friction.md`](./mechaharness-host-friction.md) (HF-05).

## Primary utility (non-negotiable)

Anything we ship for “gorgeous” must strengthen these, not compete with them:

1. **Multi-locus live state** — every currently executing node (and its
   ancestors) reads as live at once. Not a single `active_node_id` spotlight
   that hides sibling runners. Nested imagegen under `tool_call` and a sibling
   branch can both wash coral simultaneously.
2. **Non-linear motion is visible** — retries, loop rounds, nest dives, and
   fan-in joins change *where* energy sits on the fixed topology; humans should
   see the frontier move without replaying the event log.
3. **Structure stays anchored** — the graph layout is the map; execution is the
   weather. Nodes do not jump around as status changes. Zoom/pan preserve place.
4. **Spatial beats scrollback** — at a glance: what is running, what is waiting,
   what finished, what failed, what is nested under what. The event log remains
   a detail/forensics surface, not the primary mental model.
5. **Truthful data** — no fake phases, mirror lanes, or viz-only kinds. Status
   from checkpoint `status` + events; nest from `subgraph` / `child_run_id`.

Secondary (still required, but ranked under the above): dive without losing
place; soft-point bindings as plaques/inspector; parallel without spaghetti;
select → inspect.

## Design thesis (beauty serves utility)

| Utility need | MH structure | Bubble Trouble expression |
|--------------|--------------|---------------------------|
| See recipe order vs interior chatter | Outer edges = execution order; interiors stay inside chambers | Chambers mute interior until zoom; outer conduits stay readable |
| See many things running | Multiple nodes `running` + recent afterglow | Coral wash on **all** live loci; ancestors translucent-lit |
| See branching / join | Fan-out band, labeled edges | Stack band + one conduit in/out; no crossing spaghetti |
| See nest work without leaving context | `child_graph` under tool_call | Dive bubble; parent chamber stays framed |
| See bindings without clutter | Soft points as ER fields, not flow steps | Wall plaques / inspector |
| Reconstruct after the fact | Checkpoint tree + events | Dim finished structure; log for exact timestamps |

**Do not** reintroduce a second observability graph.

## Role → shape vocabulary (console)

| Role | Source | Glyph | Notes |
|------|--------|-------|-------|
| Hard / concrete step | firm graph node | Purple ridged **door tile** | Inference, tool_result, reduce, render |
| Soft nest / loop chamber | repeating, subgraph, tool/harness loops | Magenta **bubble chamber** | Title band; interior on zoom |
| Nest step / recipe-as-tool | `child_graph`, nested tool checkpoint | Soft **dive bubble** | Zoom target for child recipe |
| Config soft point | `NodeComponent` soft_point (non-tool) | Binding **plaque** | Wall layer, not outer flow |
| Flow component | turn_start, inference, tool_call, … | Interior **bead** | `then` path inside chamber |
| Parallel siblings | shared fan-out/in | **Stack band** | One conduit; cards peek |
| Boundary | layout sentinel | Start/end **hatch orb** | Optional with interior sequence |
| Live / recent / dim / failed | execution status | Coral / afterglow / cool dim / lava fault | **Multi-locus**; not exclusive highlight |

Binary soft/hard today is too coarse — and today’s single-active emphasis under-
sells true concurrent execution.

## Live frontier model

Today the world often treats one `active_node_id` as special. Target model:

- **Running set** — all nodes (at any nest depth) with checkpoint status
  `running`, plus any instance marked running in hub stacks.
- **Recent set** — nodes that completed within a short window (existing
  `recent_node_ids` from events), for afterglow of the path just taken.
- **Failed set** — failed/cancelled, visually distinct (lava fault), not merely
  dim.
- **Pending / waiting** — depends_on not yet satisfied; quieter than dim-done.
- **Ancestor glow** — parents of any running descendant read as “chamber
  occupied” so a zoomed-out view still shows where work is.

Edges on the path into a running node may pulse; idle edges stay cool. Parallel
runners ⇒ multiple pulsed conduits.

## Layout rules (spatial map, stable under live updates)

- Top-level: column topo order (already June default).
- Chamber interiors: serpentine ~3/row when wide; column when narrow; `then`
  edges stay inside.
- Outer edges never duplicate interior `then` paths.
- Soft-point plaques in a wall strip / inspector — never fake outer nodes.
- Layout identity is stable across status ticks; only fills/strokes/motion
  change for live feedback.
- Reveal thresholds stay; when small, silhouette + live wash still convey
  running vs idle.

## Visual craft (ranked under utility)

- **Frontier first** — running wash and ancestor glow beat decorative drift.
- **Chamber depth** — membrane clears on reveal so interiors (and nested live
  beads) stay readable.
- **Conduits** — directional; pulse only on paths feeding the running set.
- **Motion budget** — running wash, conduit pulse, optional chamber breathe.
  Beauty motion never obscures which loci are live.
- **Keep the void** — Bubble Trouble ground; do not flatten to MH light paper.

## Phasing

### P0 — Multi-locus live frontier + truthful nest — **landed**

- Running set / recent / failed / ancestor `occupied` from checkpoint + events
  (not single-spotlight-as-sole-signal). World exposes `running_node_ids` /
  `failed_node_ids`.
- World roles: chamber / door / bead / dive / plaque / badge.
- Serpentine interior layout for tool/loop chambers (≥3 children); edge
  `reason` → label.
- Selection inspector pane: kind, status, role, frontier, tool, child run,
  bindings (opens on select).

### P1 — Layered DAG layout + conduit feedback — **in progress**

- Pre-baked Sugiyama layout (`june.console.layered_dag`): longest-path ranks,
  barycenter crossing reduction, rank channels; orthogonal client routing.
- Soft-point plaques; richer edge pulse along live paths.
- Stack/band chrome for fan-out and multi-instance buckets.
- Failed state distinct from dim-success (partially in P0).

### P2 — Dive affordances + polish

- Clear dive cue on recipe-as-tool beads; start/end hatch orbs when useful.
- Chamber membrane / reveal craft pass — only after frontier utility is solid.

## Out of scope

- Embedding MH `recipe_diagram` SVG verbatim.
- Viz-only node kinds not backed by MH graph / `NodeComponent`.
- Mermaid / Graphviz binaries.
- Replacing the event log (it stays forensics); making the log the primary UX.
- Voice / Switchboard / side-channel observability graphs.

## Acceptance sketches

- Two fan-out branches running at once: **both** wash live; zoomed-out parent
  shows occupied chamber; log alone is not required to notice concurrency.
- Chat tools chamber: inference bead completes, `tool_call:generate_image`
  runs with nested imagegen phases lit underneath — frontier visibly moved
  into the nest without a linear “phase” storyboard.
- Several cron/chat stacks: multiple instance cards/badges can show running
  at once; finished cards stay dim and do not re-light from stale nest status.
- User who only watches the graph (ignores the log) can answer: what is
  running, what is blocked, what just finished, where is work nested.
