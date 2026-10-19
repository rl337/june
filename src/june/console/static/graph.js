/** Continuous zoom/pan graph viewport with content-sized nested nodes. */

const NS = "http://www.w3.org/2000/svg";
const MIN_ZOOM = 0.15;
const MAX_ZOOM = 8;
const CONTENT_REVEAL_PX = 110; // screen height before interiors show
const LABEL_MIN_PX = 10;

export class GraphViewport {
  constructor(svg, { onSelectNode, onStackBadge, onStackCard } = {}) {
    this.svg = svg;
    this.onSelectNode = onSelectNode;
    this.onStackBadge = onStackBadge;
    this.onStackCard = onStackCard;
    this.world = null;
    this.selectedId = null;
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this._cameraReady = false;
    this._dragging = false;
    this._dragLast = null;
    this._raf = null;
    this._index = new Map();
    this._bindInput();
  }

  setWorld(world, { preserveCamera = true } = {}) {
    this.world = world || { nodes: [], edges: [], width: 400, height: 240 };
    this._index = indexNodes(this.world.nodes || []);
    // Keep the user's camera unless this is the first frame or an explicit reset.
    if (!preserveCamera || !this._cameraReady) {
      this.fit({ clearSelection: false });
      this._cameraReady = true;
    }
    // Drop selection only if the selected node disappeared from the world.
    if (this.selectedId && !this._index.has(this.selectedId)) {
      this.selectedId = null;
    }
    this.render();
  }

  select(nodeId, { zoomToward = true } = {}) {
    const changing = this.selectedId !== nodeId;
    this.selectedId = nodeId;
    if (this.onSelectNode) this.onSelectNode(nodeId);
    if (zoomToward && changing) {
      // Center on the new selection without multiplying zoom each click.
      this._centerOnSelected({ animate: true, zoomBoost: 1 });
    } else {
      this.render();
    }
  }

  clearSelection() {
    this.selectedId = null;
    if (this.onSelectNode) this.onSelectNode("root");
    this.render();
  }

  fit({ clearSelection = true } = {}) {
    if (!this.world) return;
    const rect = this.svg.getBoundingClientRect();
    // Prefer laid-out size; fall back to attributes/parent when dialog first opens.
    const vw = Math.max(rect.width, this.svg.clientWidth, this.svg.parentElement?.clientWidth || 0, 1);
    const vh = Math.max(rect.height, this.svg.clientHeight, this.svg.parentElement?.clientHeight || 0, 1);
    const ww = Math.max(this.world.width || 400, 1);
    const wh = Math.max(this.world.height || 240, 1);
    this.zoom = clamp(Math.min(vw / ww, vh / wh) * 0.92, MIN_ZOOM, MAX_ZOOM);
    this.panX = ww / 2;
    this.panY = wh / 2;
    if (clearSelection) this.selectedId = null;
    this._cameraReady = true;
    this.render();
  }

  zoomBy(factor, { aroundSelected = true } = {}) {
    const next = clamp(this.zoom * factor, MIN_ZOOM, MAX_ZOOM);
    if (aroundSelected && this.selectedId && this._index.has(this.selectedId)) {
      this.zoom = next;
      this._centerOnSelected({ animate: false });
    } else {
      this.zoom = next;
      this.render();
    }
  }

  zoomIn() {
    this.zoomBy(1.25);
  }

  zoomOut() {
    this.zoomBy(1 / 1.25);
  }

  focusSelected() {
    if (!this.selectedId) return;
    this._centerOnSelected({ animate: true, zoomBoost: 1.6 });
  }

  _centerOnSelected({ animate = false, zoomBoost = 1 } = {}) {
    const node = this._index.get(this.selectedId);
    if (!node) {
      this.render();
      return;
    }
    const targetZoom = clamp(this.zoom * zoomBoost, MIN_ZOOM, MAX_ZOOM);
    const targetX = node.absX + node.w / 2;
    const targetY = node.absY + node.h / 2;
    if (!animate) {
      this.zoom = targetZoom;
      this.panX = targetX;
      this.panY = targetY;
      this.render();
      return;
    }
    const start = {
      zoom: this.zoom,
      panX: this.panX,
      panY: this.panY,
      t: performance.now(),
    };
    const duration = 280;
    const step = (now) => {
      const u = Math.min(1, (now - start.t) / duration);
      const e = 1 - (1 - u) ** 3;
      this.zoom = start.zoom + (targetZoom - start.zoom) * e;
      this.panX = start.panX + (targetX - start.panX) * e;
      this.panY = start.panY + (targetY - start.panY) * e;
      this.render();
      if (u < 1) this._raf = requestAnimationFrame(step);
    };
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(step);
  }

  _bindInput() {
    this.svg.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        const factor = e.deltaY > 0 ? 1 / 1.12 : 1.12;
        if (this.selectedId) {
          this.zoomBy(factor, { aroundSelected: true });
        } else {
          const before = this._screenToWorld(e.clientX, e.clientY);
          this.zoom = clamp(this.zoom * factor, MIN_ZOOM, MAX_ZOOM);
          const after = this._screenToWorld(e.clientX, e.clientY);
          this.panX += before.x - after.x;
          this.panY += before.y - after.y;
          this.render();
        }
      },
      { passive: false },
    );

    this.svg.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      if (e.target.closest(".graph-node")) return;
      this._dragging = true;
      this._dragLast = { x: e.clientX, y: e.clientY };
      this.svg.setPointerCapture(e.pointerId);
      this.svg.classList.add("is-panning");
    });
    this.svg.addEventListener("pointermove", (e) => {
      if (!this._dragging || !this._dragLast) return;
      const dx = e.clientX - this._dragLast.x;
      const dy = e.clientY - this._dragLast.y;
      this._dragLast = { x: e.clientX, y: e.clientY };
      this.panX -= dx / this.zoom;
      this.panY -= dy / this.zoom;
      this.render();
    });
    const endDrag = (e) => {
      if (!this._dragging) return;
      this._dragging = false;
      this._dragLast = null;
      this.svg.classList.remove("is-panning");
      try {
        this.svg.releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    };
    this.svg.addEventListener("pointerup", endDrag);
    this.svg.addEventListener("pointercancel", endDrag);

    this.svg.addEventListener("dblclick", (e) => {
      if (e.target.closest(".graph-node")) return;
      this.fit();
    });
  }

  _screenToWorld(clientX, clientY) {
    const rect = this.svg.getBoundingClientRect();
    const sx = clientX - rect.left;
    const sy = clientY - rect.top;
    return {
      x: this.panX + (sx - rect.width / 2) / this.zoom,
      y: this.panY + (sy - rect.height / 2) / this.zoom,
    };
  }

  _viewBox() {
    const rect = this.svg.getBoundingClientRect();
    const vw = Math.max(rect.width, 1) / this.zoom;
    const vh = Math.max(rect.height, 1) / this.zoom;
    return {
      x: this.panX - vw / 2,
      y: this.panY - vh / 2,
      w: vw,
      h: vh,
    };
  }

  render() {
    const svg = this.svg;
    const world = this.world || { nodes: [], edges: [] };
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const vb = this._viewBox();
    svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);

    const defs = el("defs");
    appendBubbleTroubleDefs(defs);
    svg.appendChild(defs);

    const root = el("g", { class: "world-root" });
    svg.appendChild(root);

    const runningIds = new Set(world.running_node_ids || []);
    drawEdges(root, world.edges || [], this._index, 0, { runningIds });
    (world.nodes || []).forEach((node) => {
      drawNodeTree(root, node, {
        absX: node.x,
        absY: node.y,
        zoom: this.zoom,
        selectedId: this.selectedId,
        runningIds,
        onSelect: (id) => this.select(id),
        onStackBadge: (n) => {
          if (this.onStackBadge) this.onStackBadge(n);
        },
        onStackCard: (n) => {
          if (this.onStackCard) this.onStackCard(n);
        },
      });
    });

    const zoomLabel = document.getElementById("zoom-level");
    if (zoomLabel) zoomLabel.textContent = `${Math.round(this.zoom * 100)}%`;
  }
}

function indexNodes(nodes, absX = 0, absY = 0, map = new Map()) {
  for (const node of nodes) {
    const x = absX + (node.x || 0);
    const y = absY + (node.y || 0);
    map.set(node.id, { ...node, absX: x, absY: y });
    if (node.children && node.children.length) {
      indexNodes(node.children, x, y, map);
    }
  }
  return map;
}

/**
 * Orthogonal conduit routing: attach to box sides and elbow through the gap
 * between nodes so paths never cut across sibling bodies.
 */
function boxOf(node, ox = 0, oy = 0) {
  return {
    id: node.id,
    x: ox + (node.absX != null ? node.absX : node.x || 0),
    y: oy + (node.absY != null ? node.absY : node.y || 0),
    w: node.w,
    h: node.h,
  };
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function routeOrthogonal(a, b, { lane = 0 } = {}) {
  const acx = a.x + a.w / 2;
  const acy = a.y + a.h / 2;
  const bcx = b.x + b.w / 2;
  const bcy = b.y + b.h / 2;
  const dx = bcx - acx;
  const dy = bcy - acy;
  const pad = 6;
  const laneNudge = lane * 10;

  // Prefer the dominant axis; layered top-level graphs are left→right.
  if (Math.abs(dx) >= Math.abs(dy) * 0.55) {
    const leftToRight = dx >= 0;
    const x1 = leftToRight ? a.x + a.w : a.x;
    const x2 = leftToRight ? b.x : b.x + b.w;
    const y1 = clamp(bcy, a.y + pad, a.y + a.h - pad) + laneNudge;
    const y2 = clamp(bcy, b.y + pad, b.y + b.h - pad);
    // Channel midX sits strictly between the two boxes.
    const gapLeft = leftToRight ? a.x + a.w : b.x + b.w;
    const gapRight = leftToRight ? b.x : a.x;
    let midX = (gapLeft + gapRight) / 2 + laneNudge;
    if (gapRight - gapLeft > pad * 2) {
      midX = clamp(midX, gapLeft + pad, gapRight - pad);
    }
    if (Math.abs(y1 - y2) < 1.5) {
      return {
        d: `M ${x1} ${y1} L ${x2} ${y2}`,
        labelX: (x1 + x2) / 2,
        labelY: y1 - 8,
      };
    }
    return {
      d: `M ${x1} ${y1} L ${midX} ${y1} L ${midX} ${y2} L ${x2} ${y2}`,
      labelX: midX + 8,
      labelY: (y1 + y2) / 2,
    };
  }

  // Vertical primary (column interiors).
  const topToBottom = dy >= 0;
  const y1 = topToBottom ? a.y + a.h : a.y;
  const y2 = topToBottom ? b.y : b.y + b.h;
  const x1 = clamp(acx, a.x + pad, a.x + a.w - pad) + laneNudge;
  const x2 = clamp(bcx, b.x + pad, b.x + b.w - pad);
  const gapTop = topToBottom ? a.y + a.h : b.y + b.h;
  const gapBottom = topToBottom ? b.y : a.y;
  let midY = (gapTop + gapBottom) / 2 + laneNudge;
  if (gapBottom - gapTop > pad * 2) {
    midY = clamp(midY, gapTop + pad, gapBottom - pad);
  }
  if (Math.abs(x1 - x2) < 1.5) {
    return {
      d: `M ${x1} ${y1} L ${x2} ${y2}`,
      labelX: x1 + 8,
      labelY: (y1 + y2) / 2,
    };
  }
  return {
    d: `M ${x1} ${y1} L ${x1} ${midY} L ${x2} ${midY} L ${x2} ${y2}`,
    labelX: (x1 + x2) / 2,
    labelY: midY - 8,
  };
}

function drawEdges(layer, edges, index, depth, { runningIds = new Set() } = {}) {
  // Group fan-out from the same source so elbows take distinct lanes.
  const fanCount = new Map();
  for (const edge of edges) {
    fanCount.set(edge.from, (fanCount.get(edge.from) || 0) + 1);
  }
  const fanSeen = new Map();
  for (const edge of edges) {
    const a = index.get(edge.from);
    const b = index.get(edge.to);
    if (!a || !b) continue;
    const live =
      runningIds.has(edge.to) ||
      b.execution === "running" ||
      b.execution === "occupied" ||
      a.execution === "running";
    let lane = 0;
    if ((fanCount.get(edge.from) || 0) > 1) {
      const seen = fanSeen.get(edge.from) || 0;
      fanSeen.set(edge.from, seen + 1);
      // Center lanes around 0: … -1, 0, 1 …
      const n = fanCount.get(edge.from);
      lane = seen - (n - 1) / 2;
    }
    const route = routeOrthogonal(boxOf(a), boxOf(b), { lane });
    const path = el("path", {
      d: route.d,
      fill: "none",
      stroke: live ? "#ff5eb0" : depth === 0 ? "#6a4cb8" : "#2ad49a",
      "stroke-width": live ? 2.4 : depth === 0 ? 2 : 1.2,
      "stroke-opacity": live ? "0.95" : "0.85",
      "stroke-linejoin": "round",
      "stroke-linecap": "round",
      class: `graph-edge${live ? " is-live" : ""}`,
      "marker-end": live ? "url(#edgeArrowLive)" : "url(#edgeArrow)",
    });
    layer.appendChild(path);
    if (edge.label) {
      const label = el("text", {
        x: route.labelX,
        y: route.labelY,
        class: "edge-label",
        "font-size": depth === 0 ? 10 : 9,
      });
      label.textContent = truncate(edge.label, depth === 0 ? 28 : 20);
      layer.appendChild(label);
    }
  }
}

function subtreeRunning(node) {
  if (
    node.execution === "running" ||
    node.execution === "occupied" ||
    node.status === "running"
  ) {
    return true;
  }
  // Finished stack cards must not inherit stale nested "running" bits.
  if (node.stack_role === "front" || node.stack_role === "back") return false;
  return (node.children || []).some((c) => subtreeRunning(c));
}

function nodeFrontier(node) {
  if (node.execution === "failed" || node.status === "failed" || node.status === "cancelled") {
    return "failed";
  }
  if (node.execution === "running" || node.status === "running") return "running";
  if (node.execution === "occupied") return "occupied";
  if (node.execution === "recent") return "recent";
  if (node.execution === "dim") return "dim";
  return node.execution || "pending";
}

function drawNodeTree(layer, node, ctx) {
  const absX = ctx.absX;
  const absY = ctx.absY;
  const screenH = node.h * ctx.zoom;
  const role = node.stack_role || "";
  // Stacked instance cards are entry points to the watch dialog — keep them
  // collapsed on the main graph so nested steps cannot steal the click.
  const reveal =
    role !== "front" &&
    role !== "back" &&
    screenH >= CONTENT_REVEAL_PX &&
    (node.children || []).length > 0;
  const selected = ctx.selectedId === node.id;
  const frontier = nodeFrontier(node);
  const live = frontier === "running" || frontier === "occupied" || subtreeRunning(node);
  const glyph = node.role || (node.shape === "round_rect" ? "chamber" : "door");

  const g = el("g", {
    class: `graph-node node role-${glyph} ${frontier}${selected ? " is-selected" : ""}${
      role ? ` stack-${role}` : ""
    }`,
    transform: `translate(${absX} ${absY})`,
  });
  g.dataset.nodeId = node.id;
  g.dataset.role = glyph;
  g.dataset.frontier = frontier;
  g.style.cursor = "pointer";
  const openStack = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (ctx.onStackBadge) ctx.onStackBadge(node);
  };
  if (role === "badge") {
    g.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      openStack(e);
    });
    g.addEventListener("click", openStack);
    g.addEventListener("dblclick", openStack);
  } else if (role === "front" || role === "back") {
    const openCard = (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (ctx.onStackCard) ctx.onStackCard(node);
      else if (ctx.onSelect) ctx.onSelect(node.id);
    };
    g.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      openCard(e);
    });
    g.addEventListener("click", openCard);
    g.addEventListener("dblclick", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (ctx.onStackBadge) ctx.onStackBadge(node);
      else openCard(e);
    });
  } else {
    g.addEventListener("click", (e) => {
      e.stopPropagation();
      ctx.onSelect(node.id);
    });
  }

  // Role → Bubble Trouble glyph. Chambers/dives are soft membranes; doors are
  // ridged tiles; beads are compact coral/magenta pills.
  const soft = glyph !== "door";
  let rx;
  if (glyph === "dive") rx = Math.min(28, Math.max(16, node.h * 0.36));
  else if (glyph === "bead") rx = Math.min(18, Math.max(12, node.h * 0.42));
  else if (glyph === "chamber" || glyph === "badge")
    rx = Math.min(26, Math.max(14, node.h * 0.28));
  else if (glyph === "plaque") rx = 10;
  else rx = 4;

  let fill;
  let opacity;
  if (frontier === "failed") {
    fill = "#7a1020";
    opacity = reveal ? "0.45" : "0.88";
  } else if (frontier === "running") {
    fill = soft ? "#e85a4f" : "#ff5eb0";
    opacity = reveal ? "0.28" : "0.85";
  } else if (frontier === "occupied") {
    fill = soft ? "#8a2858" : "#6a3a90";
    opacity = reveal ? "0.22" : "0.7";
  } else if (frontier === "recent") {
    fill = soft ? "#5a2048" : "#4a3a7a";
    opacity = reveal ? "0.24" : "0.75";
  } else {
    fill = soft ? "#4a1848" : "#3a2a6e";
    opacity = reveal ? "0.26" : "0.9";
  }
  const stroke =
    selected
      ? "#5eeaff"
      : frontier === "failed"
        ? "#ff3b2f"
        : frontier === "running"
          ? "#ffffff"
          : frontier === "occupied"
            ? "#ff8ec8"
            : soft
              ? "#ff5eb0"
              : "#2ad49a";
  const rect = el("rect", {
    x: 0,
    y: 0,
    width: node.w,
    height: node.h,
    rx,
    ry: rx,
    fill,
    "fill-opacity": opacity,
    stroke,
    "stroke-width": selected ? 3 : live ? 2.35 : 1.25,
  });
  if (frontier === "running") rect.setAttribute("filter", "url(#glow)");
  else if (frontier === "occupied") rect.setAttribute("filter", "url(#glowOccupied)");
  g.dataset.running = frontier === "running" ? "1" : "0";
  g.dataset.shape = soft ? "soft" : "hard";
  g.appendChild(rect);

  if (soft) {
    appendBubbleSpecular(g, node.w, node.h, rx, {
      running: frontier === "running",
      reveal,
      occupied: frontier === "occupied",
    });
  } else {
    appendTileTexture(g, node.w, node.h, rx, { reveal });
  }

  if (node.label && screenH >= LABEL_MIN_PX) {
    const label = el("text", {
      x: node.w / 2,
      y: reveal ? 18 : node.h / 2 + 4,
      "text-anchor": "middle",
      class: "node-label",
      "font-size": reveal ? 12 : Math.min(14, Math.max(9, 12 / Math.sqrt(ctx.zoom))),
    });
    label.textContent = truncate(node.label, reveal ? 28 : 18);
    g.appendChild(label);
  }

  if (reveal) {
    const inner = el("g", { class: "node-interior" });
    const interiorKids = (node.children || []).filter(
      (c) => c.stack_role !== "front" && c.stack_role !== "back" && c.stack_role !== "badge",
    );
    const fanCount = new Map();
    for (const edge of node.edges || []) {
      fanCount.set(edge.from, (fanCount.get(edge.from) || 0) + 1);
    }
    const fanSeen = new Map();
    for (const edge of node.edges || []) {
      const a = interiorKids.find((c) => c.id === edge.from);
      const b = interiorKids.find((c) => c.id === edge.to);
      if (!a || !b) continue;
      const childLive =
        b.execution === "running" ||
        b.execution === "occupied" ||
        a.execution === "running";
      let lane = 0;
      if ((fanCount.get(edge.from) || 0) > 1) {
        const seen = fanSeen.get(edge.from) || 0;
        fanSeen.set(edge.from, seen + 1);
        const n = fanCount.get(edge.from);
        lane = seen - (n - 1) / 2;
      }
      const route = routeOrthogonal(
        { id: a.id, x: a.x || 0, y: a.y || 0, w: a.w, h: a.h },
        { id: b.id, x: b.x || 0, y: b.y || 0, w: b.w, h: b.h },
        { lane },
      );
      inner.appendChild(
        el("path", {
          d: route.d,
          fill: "none",
          stroke: childLive ? "#ff5eb0" : "#6a4cb8",
          "stroke-width": childLive ? 1.8 : 1.25,
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
          class: `graph-edge${childLive ? " is-live" : ""}`,
          "marker-end": childLive ? "url(#edgeArrowLive)" : "url(#edgeArrow)",
        }),
      );
      if (edge.label) {
        const t = el("text", {
          x: route.labelX,
          y: route.labelY,
          class: "edge-label",
          "font-size": 9,
        });
        t.textContent = truncate(edge.label, 20);
        inner.appendChild(t);
      }
    }
    const kids = [...(node.children || [])].sort((a, b) => {
      const da = a.stack_role === "badge" ? 1e9 : a.stack_depth || 0;
      const db = b.stack_role === "badge" ? 1e9 : b.stack_depth || 0;
      return da - db;
    });
    for (const child of kids) {
      drawNodeTree(inner, child, {
        absX: child.x || 0,
        absY: child.y || 0,
        zoom: ctx.zoom,
        selectedId: ctx.selectedId,
        runningIds: ctx.runningIds,
        onSelect: ctx.onSelect,
        onStackBadge: ctx.onStackBadge,
        onStackCard: ctx.onStackCard,
      });
    }
    g.appendChild(inner);
  } else {
    const badge = (node.children || []).find((c) => c.stack_role === "badge");
    if (badge) {
      const inner = el("g", { class: "node-interior node-interior--badge-only" });
      const bx = Math.max(6, node.w - badge.w - 6);
      const by = Math.max(6, (node.h - badge.h) / 2);
      drawNodeTree(inner, badge, {
        absX: bx,
        absY: by,
        zoom: ctx.zoom,
        selectedId: ctx.selectedId,
        runningIds: ctx.runningIds,
        onSelect: ctx.onSelect,
        onStackBadge: ctx.onStackBadge,
        onStackCard: ctx.onStackCard,
      });
      g.appendChild(inner);
    }
  }

  layer.appendChild(g);
}

function appendBubbleTroubleDefs(defs) {
  // Magenta/coral running glow (Norfair energy, not green-only).
  const glow = el("filter", { id: "glow" });
  glow.innerHTML =
    '<feGaussianBlur stdDeviation="3.5" result="b"/><feColorMatrix in="b" type="matrix" values="0 0 0 0 1  0 0 0 0 0.35  0 0 0 0 0.55  0 0 0 0.8 0" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>';
  defs.appendChild(glow);

  const glowOcc = el("filter", { id: "glowOccupied" });
  glowOcc.innerHTML =
    '<feGaussianBlur stdDeviation="2.2" result="b"/><feColorMatrix in="b" type="matrix" values="0 0 0 0 1  0 0 0 0 0.45  0 0 0 0 0.7  0 0 0 0.45 0" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>';
  defs.appendChild(glowOcc);

  const arrow = el("marker", {
    id: "edgeArrow",
    viewBox: "0 0 10 10",
    refX: "9",
    refY: "5",
    markerWidth: "6",
    markerHeight: "6",
    orient: "auto-start-reverse",
  });
  arrow.appendChild(el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#6a4cb8" }));
  defs.appendChild(arrow);
  const arrowLive = el("marker", {
    id: "edgeArrowLive",
    viewBox: "0 0 10 10",
    refX: "9",
    refY: "5",
    markerWidth: "7",
    markerHeight: "7",
    orient: "auto-start-reverse",
  });
  arrowLive.appendChild(el("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: "#ff5eb0" }));
  defs.appendChild(arrowLive);

  // Idle magenta membrane sheen.
  const sheen = el("radialGradient", {
    id: "bubbleSheen",
    cx: "0.28",
    cy: "0.24",
    r: "0.78",
    gradientUnits: "objectBoundingBox",
  });
  sheen.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0.72" }));
  sheen.appendChild(el("stop", { offset: "20%", "stop-color": "#ffb0d8", "stop-opacity": "0.28" }));
  sheen.appendChild(el("stop", { offset: "55%", "stop-color": "#4a1848", "stop-opacity": "0.06" }));
  sheen.appendChild(el("stop", { offset: "100%", "stop-color": "#050208", "stop-opacity": "0" }));
  defs.appendChild(sheen);

  // Running coral bubble-core sheen (red Norfair tiles).
  const sheenRun = el("radialGradient", {
    id: "bubbleSheenRun",
    cx: "0.3",
    cy: "0.28",
    r: "0.72",
    gradientUnits: "objectBoundingBox",
  });
  sheenRun.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0.8" }));
  sheenRun.appendChild(el("stop", { offset: "22%", "stop-color": "#ffc4b8", "stop-opacity": "0.35" }));
  sheenRun.appendChild(el("stop", { offset: "55%", "stop-color": "#e85a4f", "stop-opacity": "0.12" }));
  sheenRun.appendChild(el("stop", { offset: "100%", "stop-color": "#2a0810", "stop-opacity": "0" }));
  defs.appendChild(sheenRun);

  const hot = el("radialGradient", {
    id: "bubbleHot",
    cx: "0.5",
    cy: "0.5",
    r: "0.5",
    gradientUnits: "objectBoundingBox",
  });
  hot.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0.92" }));
  hot.appendChild(el("stop", { offset: "40%", "stop-color": "#ffe8f4", "stop-opacity": "0.4" }));
  hot.appendChild(el("stop", { offset: "100%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  defs.appendChild(hot);

  const rim = el("linearGradient", {
    id: "bubbleRim",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
    gradientUnits: "objectBoundingBox",
  });
  rim.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  rim.appendChild(el("stop", { offset: "70%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  rim.appendChild(el("stop", { offset: "100%", "stop-color": "#ff5eb0", "stop-opacity": "0.22" }));
  defs.appendChild(rim);

  // Muted purple ridged doors + magenta fuzzy platform tiles (Norfair).
  const tile = el("pattern", {
    id: "metroidTile",
    width: 16,
    height: 16,
    patternUnits: "userSpaceOnUse",
  });
  tile.appendChild(el("rect", { width: "16", height: "16", fill: "#1a1230" }));
  tile.appendChild(
    el("rect", {
      x: "0.5",
      y: "0.5",
      width: "15",
      height: "15",
      fill: "#4a3a8a",
      stroke: "#7a68c8",
      "stroke-width": "1",
    }),
  );
  // Horizontal door ridges
  for (const y of [4, 8, 12]) {
    tile.appendChild(
      el("line", {
        x1: "1.5",
        y1: String(y),
        x2: "14.5",
        y2: String(y),
        stroke: "#a02040",
        "stroke-opacity": "0.45",
        "stroke-width": "0.9",
      }),
    );
  }
  // Soft magenta “fuzzy” tile center (muted platform motif)
  tile.appendChild(
    el("circle", {
      cx: "8",
      cy: "8",
      r: "3.2",
      fill: "#2a1030",
      stroke: "#c04090",
      "stroke-opacity": "0.4",
      "stroke-width": "0.8",
    }),
  );
  tile.appendChild(
    el("ellipse", {
      cx: "6.8",
      cy: "6.6",
      rx: "1.1",
      ry: "0.75",
      fill: "#ffffff",
      opacity: "0.22",
    }),
  );
  defs.appendChild(tile);
}

function appendBubbleSpecular(g, w, h, rx, { running, reveal, occupied = false }) {
  const sheen = el("rect", {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx,
    ry: rx,
    fill: running ? "url(#bubbleSheenRun)" : "url(#bubbleSheen)",
    "fill-opacity": reveal ? "0.95" : occupied ? "0.85" : "1",
    "pointer-events": "none",
    class: "bubble-sheen",
  });
  g.appendChild(sheen);

  const rim = el("rect", {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx,
    ry: rx,
    fill: "url(#bubbleRim)",
    "pointer-events": "none",
    class: "bubble-rim",
  });
  g.appendChild(rim);

  const glintR = Math.min(w, h);
  // White crescent arc — hallmark of Norfair coral bubble tiles.
  const crescent = el("path", {
    d: crescentPath(w * 0.22, h * 0.2, Math.max(10, glintR * 0.2), Math.max(6, glintR * 0.12)),
    fill: "none",
    stroke: "#ffffff",
    "stroke-width": Math.max(1.6, glintR * 0.025),
    "stroke-linecap": "round",
    "stroke-opacity": running ? "0.9" : "0.7",
    "pointer-events": "none",
    class: "bubble-crescent",
  });
  g.appendChild(crescent);

  const hot = el("ellipse", {
    cx: w * 0.24,
    cy: h * 0.18,
    rx: Math.max(7, glintR * 0.14),
    ry: Math.max(4, glintR * 0.08),
    fill: "url(#bubbleHot)",
    "pointer-events": "none",
    class: "bubble-hot",
  });
  g.appendChild(hot);

  const hot2 = el("ellipse", {
    cx: w * 0.36,
    cy: h * 0.28,
    rx: Math.max(2.8, glintR * 0.05),
    ry: Math.max(1.8, glintR * 0.03),
    fill: "#ffffff",
    "fill-opacity": running ? "0.55" : "0.4",
    "pointer-events": "none",
    class: "bubble-hot-secondary",
  });
  g.appendChild(hot2);
}

function crescentPath(cx, cy, rx, ry) {
  // Simple open arc in the upper-left quadrant.
  const x1 = cx - rx * 0.15;
  const y1 = cy + ry * 0.75;
  const x2 = cx + rx * 0.85;
  const y2 = cy - ry * 0.15;
  return `M ${x1} ${y1} A ${rx} ${ry} 0 0 1 ${x2} ${y2}`;
}

function appendTileTexture(g, w, h, rx, { reveal }) {
  const tex = el("rect", {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx,
    ry: rx,
    fill: "url(#metroidTile)",
    "fill-opacity": reveal ? "0.28" : "0.4",
    "pointer-events": "none",
    class: "tile-texture",
  });
  g.appendChild(tex);
}

function el(name, attrs = {}) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null) continue;
    if (k === "class") node.setAttribute("class", v);
    else node.setAttribute(k, String(v));
  }
  return node;
}

function truncate(text, max) {
  const s = String(text || "");
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

/** @deprecated use GraphViewport */
export function renderGraph(canvas, snapshot, opts = {}) {
  if (!canvas._viewport) {
    canvas._viewport = new GraphViewport(canvas, opts);
  }
  canvas._viewport.setWorld(snapshot.world || emptyWorldFromScene(snapshot.scene), {
    preserveCamera: true,
  });
  return canvas._viewport;
}

function emptyWorldFromScene(scene) {
  return {
    root_id: "root",
    goal: (scene && scene.scene_title) || "",
    width: 400,
    height: 240,
    nodes: [],
    edges: [],
  };
}

export async function selectScene(nodeId) {
  await fetch("/api/scene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId || "root" }),
  });
}
