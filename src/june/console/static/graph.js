/** Continuous zoom/pan graph viewport with content-sized nested nodes. */

const NS = "http://www.w3.org/2000/svg";
const MIN_ZOOM = 0.15;
const MAX_ZOOM = 8;
const CONTENT_REVEAL_PX = 110; // screen height before interiors show
const LABEL_MIN_PX = 10;

export class GraphViewport {
  constructor(svg, { onSelectNode, onStackBadge } = {}) {
    this.svg = svg;
    this.onSelectNode = onSelectNode;
    this.onStackBadge = onStackBadge;
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
    const vw = Math.max(rect.width, 1);
    const vh = Math.max(rect.height, 1);
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
    const glow = el("filter", { id: "glow" });
    glow.innerHTML =
      '<feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>';
    defs.appendChild(glow);
    svg.appendChild(defs);

    const root = el("g", { class: "world-root" });
    svg.appendChild(root);

    drawEdges(root, world.edges || [], this._index, 0);
    (world.nodes || []).forEach((node) => {
      drawNodeTree(root, node, {
        absX: node.x,
        absY: node.y,
        zoom: this.zoom,
        selectedId: this.selectedId,
        onSelect: (id) => this.select(id),
        onStackBadge: (n) => {
          if (this.onStackBadge) this.onStackBadge(n);
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

function drawEdges(layer, edges, index, depth) {
  for (const edge of edges) {
    const a = index.get(edge.from);
    const b = index.get(edge.to);
    if (!a || !b) continue;
    const line = el("line", {
      x1: a.absX + a.w / 2,
      y1: a.absY + a.h / 2,
      x2: b.absX + b.w / 2,
      y2: b.absY + b.h / 2,
      stroke: depth === 0 ? "#4b5c78" : "#6a7d99",
      "stroke-width": depth === 0 ? 2 : 1.2,
      "stroke-opacity": "0.85",
      class: "graph-edge",
    });
    layer.appendChild(line);
  }
}

function subtreeRunning(node) {
  if (node.execution === "running" || node.status === "running") return true;
  // Finished stack cards must not inherit stale nested "running" bits.
  if (node.stack_role === "front" || node.stack_role === "back") return false;
  return (node.children || []).some((c) => subtreeRunning(c));
}

function drawNodeTree(layer, node, ctx) {
  const absX = ctx.absX;
  const absY = ctx.absY;
  const screenH = node.h * ctx.zoom;
  const reveal = screenH >= CONTENT_REVEAL_PX && (node.children || []).length > 0;
  const selected = ctx.selectedId === node.id;
  const running = subtreeRunning(node);
  const role = node.stack_role || "";

  const g = el("g", {
    class: `graph-node node ${running ? "running" : node.execution || "pending"}${
      selected ? " is-selected" : ""
    }${role ? ` stack-${role}` : ""}`,
    transform: `translate(${absX} ${absY})`,
  });
  g.dataset.nodeId = node.id;
  g.style.cursor = "pointer";
  g.addEventListener("click", (e) => {
    e.stopPropagation();
    if (role === "badge" && ctx.onStackBadge) {
      ctx.onStackBadge(node);
      return;
    }
    ctx.onSelect(node.id);
  });
  g.addEventListener("dblclick", (e) => {
    e.stopPropagation();
    if ((role === "badge" || role === "front" || role === "back") && ctx.onStackBadge) {
      ctx.onStackBadge(node);
    }
  });

  // Idle purple vs lighter running wash. Collapsed nodes keep the running
  // wash when any descendant is live — do not fall back to solid idle purple.
  const soft = node.shape === "round_rect";
  let fill;
  let opacity;
  if (running) {
    fill = soft ? "#c4b5fd" : "#7dd3fc";
    // Collapsed: stay clearly lit; revealed: light wash over children.
    opacity = reveal ? "0.30" : "0.78";
  } else {
    fill = soft ? "#7c5cbf" : "#3d6fb8";
    opacity = reveal ? "0.22" : "0.92";
  }
  const rect = el("rect", {
    x: 0,
    y: 0,
    width: node.w,
    height: node.h,
    rx: soft ? 16 : 4,
    ry: soft ? 16 : 4,
    fill,
    "fill-opacity": opacity,
    stroke: selected ? "#f5c542" : running ? "#5eead4" : "#dfe7f5",
    "stroke-width": selected ? 3 : running ? 2.25 : 1.25,
  });
  if (running) rect.setAttribute("filter", "url(#glow)");
  g.dataset.running = running ? "1" : "0";
  g.appendChild(rect);

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
    for (const edge of node.edges || []) {
      const a = (node.children || []).find((c) => c.id === edge.from);
      const b = (node.children || []).find((c) => c.id === edge.to);
      if (!a || !b) continue;
      inner.appendChild(
        el("line", {
          x1: a.x + a.w / 2,
          y1: a.y + a.h / 2,
          x2: b.x + b.w / 2,
          y2: b.y + b.h / 2,
          stroke: "#8aa0c0",
          "stroke-width": 1.25,
          class: "graph-edge",
        }),
      );
    }
    // Paint stacked cards back→front so overlap is correct.
    const kids = [...(node.children || [])].sort(
      (a, b) => (a.stack_depth || 0) - (b.stack_depth || 0),
    );
    for (const child of kids) {
      drawNodeTree(inner, child, {
        absX: child.x || 0,
        absY: child.y || 0,
        zoom: ctx.zoom,
        selectedId: ctx.selectedId,
        onSelect: ctx.onSelect,
        onStackBadge: ctx.onStackBadge,
      });
    }
    g.appendChild(inner);
  }

  layer.appendChild(g);
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

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
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
