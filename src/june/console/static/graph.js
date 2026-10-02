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
    appendBubbleTroubleDefs(defs);
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
      stroke: depth === 0 ? "#3d6b52" : "#5a8f6e",
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

  // Bubble Trouble palette: membrane green idle, bright bubble cyan running.
  const soft = node.shape === "round_rect";
  const rx = soft ? Math.min(26, Math.max(14, node.h * 0.28)) : 4;
  let fill;
  let opacity;
  if (running) {
    fill = soft ? "#5dffb0" : "#3de0ff";
    opacity = reveal ? "0.28" : "0.78";
  } else {
    fill = soft ? "#1f6b45" : "#1a5a66";
    opacity = reveal ? "0.24" : "0.9";
  }
  const rect = el("rect", {
    x: 0,
    y: 0,
    width: node.w,
    height: node.h,
    rx,
    ry: rx,
    fill,
    "fill-opacity": opacity,
    stroke: selected ? "#ffb347" : running ? "#c8ffe8" : "#7eab8f",
    "stroke-width": selected ? 3 : running ? 2.35 : 1.25,
  });
  if (running) rect.setAttribute("filter", "url(#glow)");
  g.dataset.running = running ? "1" : "0";
  g.dataset.shape = soft ? "soft" : "hard";
  g.appendChild(rect);

  // Soft/circular-ish nodes: glass bubble specular. Hard rects: muted Metroid tiles.
  if (soft) {
    appendBubbleSpecular(g, node.w, node.h, rx, { running, reveal });
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
          stroke: "#5a8f6e",
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

function appendBubbleTroubleDefs(defs) {
  const glow = el("filter", { id: "glow" });
  glow.innerHTML =
    '<feGaussianBlur stdDeviation="3.5" result="b"/><feColorMatrix in="b" type="matrix" values="0 0 0 0 0.36  0 0 0 0 1  0 0 0 0 0.69  0 0 0 0.75 0" result="g"/><feMerge><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/></feMerge>';
  defs.appendChild(glow);

  // Soft bubble body sheen (top-left light wrap).
  const sheen = el("radialGradient", {
    id: "bubbleSheen",
    cx: "0.28",
    cy: "0.24",
    r: "0.78",
    gradientUnits: "objectBoundingBox",
  });
  sheen.appendChild(el("stop", { offset: "0%", "stop-color": "#f4fff9", "stop-opacity": "0.55" }));
  sheen.appendChild(el("stop", { offset: "28%", "stop-color": "#9dffd4", "stop-opacity": "0.22" }));
  sheen.appendChild(el("stop", { offset: "62%", "stop-color": "#1f6b45", "stop-opacity": "0.06" }));
  sheen.appendChild(el("stop", { offset: "100%", "stop-color": "#040806", "stop-opacity": "0" }));
  defs.appendChild(sheen);

  const sheenRun = el("radialGradient", {
    id: "bubbleSheenRun",
    cx: "0.28",
    cy: "0.24",
    r: "0.78",
    gradientUnits: "objectBoundingBox",
  });
  sheenRun.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0.62" }));
  sheenRun.appendChild(el("stop", { offset: "30%", "stop-color": "#c8ffe8", "stop-opacity": "0.28" }));
  sheenRun.appendChild(el("stop", { offset: "70%", "stop-color": "#5dffb0", "stop-opacity": "0.08" }));
  sheenRun.appendChild(el("stop", { offset: "100%", "stop-color": "#041810", "stop-opacity": "0" }));
  defs.appendChild(sheenRun);

  // Tight specular glint.
  const hot = el("radialGradient", {
    id: "bubbleHot",
    cx: "0.5",
    cy: "0.5",
    r: "0.5",
    gradientUnits: "objectBoundingBox",
  });
  hot.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0.85" }));
  hot.appendChild(el("stop", { offset: "45%", "stop-color": "#e8fff4", "stop-opacity": "0.35" }));
  hot.appendChild(el("stop", { offset: "100%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  defs.appendChild(hot);

  // Lower rim refraction for bubble depth.
  const rim = el("linearGradient", {
    id: "bubbleRim",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1",
    gradientUnits: "objectBoundingBox",
  });
  rim.appendChild(el("stop", { offset: "0%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  rim.appendChild(el("stop", { offset: "68%", "stop-color": "#ffffff", "stop-opacity": "0" }));
  rim.appendChild(el("stop", { offset: "100%", "stop-color": "#9dffd4", "stop-opacity": "0.18" }));
  defs.appendChild(rim);

  // Muted Metroid-style tiled blocks with bubbly column holes.
  const tile = el("pattern", {
    id: "metroidTile",
    width: 14,
    height: 14,
    patternUnits: "userSpaceOnUse",
  });
  tile.appendChild(el("rect", { width: "14", height: "14", fill: "#081912" }));
  tile.appendChild(
    el("rect", {
      x: "0.5",
      y: "0.5",
      width: "13",
      height: "13",
      fill: "#154030",
      stroke: "#2d6b4c",
      "stroke-width": "1.1",
    }),
  );
  tile.appendChild(
    el("line", {
      x1: "0.5",
      y1: "0.5",
      x2: "13.5",
      y2: "0.5",
      stroke: "#3a7d5a",
      "stroke-opacity": "0.35",
      "stroke-width": "0.7",
    }),
  );
  // Bubble cutout in the block (classic Metroid wall motif).
  tile.appendChild(
    el("circle", {
      cx: "7",
      cy: "7",
      r: "3.4",
      fill: "#040d09",
      stroke: "#3f8a5e",
      "stroke-width": "0.9",
    }),
  );
  tile.appendChild(
    el("ellipse", {
      cx: "5.9",
      cy: "5.8",
      rx: "1.15",
      ry: "0.8",
      fill: "#5aa876",
      opacity: "0.32",
    }),
  );
  defs.appendChild(tile);
}

function appendBubbleSpecular(g, w, h, rx, { running, reveal }) {
  const sheen = el("rect", {
    x: 0,
    y: 0,
    width: w,
    height: h,
    rx,
    ry: rx,
    fill: running ? "url(#bubbleSheenRun)" : "url(#bubbleSheen)",
    "fill-opacity": reveal ? "0.85" : "1",
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
  const hot = el("ellipse", {
    cx: w * 0.27,
    cy: h * 0.22,
    rx: Math.max(6, glintR * 0.13),
    ry: Math.max(3.5, glintR * 0.075),
    fill: "url(#bubbleHot)",
    "pointer-events": "none",
    class: "bubble-hot",
  });
  g.appendChild(hot);

  // Secondary smaller glint for glass depth.
  const hot2 = el("ellipse", {
    cx: w * 0.38,
    cy: h * 0.3,
    rx: Math.max(2.5, glintR * 0.045),
    ry: Math.max(1.6, glintR * 0.028),
    fill: "#ffffff",
    "fill-opacity": running ? "0.45" : "0.28",
    "pointer-events": "none",
    class: "bubble-hot-secondary",
  });
  g.appendChild(hot2);
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
    "fill-opacity": reveal ? "0.16" : "0.28",
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
