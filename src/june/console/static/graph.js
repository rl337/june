/** Graph SVG rendering inside the graph view pane. */

const NODE_W = 132;
const NODE_H = 44;
const LAYER_Y = { foreground: 120, background: 250 };

export function renderGraph(canvas, snapshot, { onSelectNode } = {}) {
  if (!canvas) return;
  const scene = snapshot.scene || {};
  const nodes = scene.nodes || [];
  const edges = scene.edges || [];
  const fg = nodes.filter((n) => n.layer === "foreground");
  const bg = nodes.filter((n) => n.layer === "background");

  while (canvas.firstChild) canvas.removeChild(canvas.firstChild);

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  const glow = document.createElementNS("http://www.w3.org/2000/svg", "filter");
  glow.setAttribute("id", "glow");
  glow.innerHTML =
    '<feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>';
  defs.appendChild(glow);
  canvas.appendChild(defs);

  const edgeLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  const nodeLayer = document.createElementNS("http://www.w3.org/2000/svg", "g");
  canvas.appendChild(edgeLayer);
  canvas.appendChild(nodeLayer);

  const positions = layoutNodes(fg, bg);
  edges.forEach((e) => drawEdge(edgeLayer, positions, e.from, e.to));
  nodes.forEach((n) =>
    drawNode(nodeLayer, n, positions.get(n.id), () => {
      if (onSelectNode) onSelectNode(n.id);
    }),
  );
}

function layoutNodes(foreground, background) {
  const positions = new Map();
  const placeRow = (row, y) => {
    const gap = 24;
    const totalW = row.length * NODE_W + Math.max(0, row.length - 1) * gap;
    let x = (960 - totalW) / 2;
    row.forEach((n) => {
      positions.set(n.id, { x, y, node: n });
      x += NODE_W + gap;
    });
  };
  placeRow(foreground, LAYER_Y.foreground);
  placeRow(background, LAYER_Y.background);
  return positions;
}

function drawEdge(layer, positions, from, to) {
  const a = positions.get(from);
  const b = positions.get(to);
  if (!a || !b) return;
  const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
  line.setAttribute("x1", String(a.x + NODE_W / 2));
  line.setAttribute("y1", String(a.y + NODE_H));
  line.setAttribute("x2", String(b.x + NODE_W / 2));
  line.setAttribute("y2", String(b.y));
  line.setAttribute("stroke", "#4b5c78");
  line.setAttribute("stroke-width", "1.5");
  layer.appendChild(line);
}

function drawNode(layer, node, pos, onClick) {
  if (!pos) return;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("node", node.execution || "pending");
  g.style.cursor = node.layer === "foreground" ? "pointer" : "default";
  if (node.layer === "foreground" && onClick) {
    g.addEventListener("click", () => onClick());
  }

  const fill = node.shape === "round_rect" ? "#7c5cbf" : "#3d6fb8";
  const shape = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  if (node.shape === "round_rect") {
    shape.setAttribute("rx", "14");
    shape.setAttribute("ry", "14");
  }
  shape.setAttribute("x", String(pos.x));
  shape.setAttribute("y", String(pos.y));
  shape.setAttribute("width", String(NODE_W));
  shape.setAttribute("height", String(NODE_H));
  shape.setAttribute("fill", fill);
  shape.setAttribute("stroke", "#dfe7f5");
  shape.setAttribute("stroke-width", "1");
  if (node.execution === "running") {
    shape.setAttribute("filter", "url(#glow)");
  }
  g.appendChild(shape);

  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", String(pos.x + NODE_W / 2));
  label.setAttribute("y", String(pos.y + NODE_H / 2 + 4));
  label.setAttribute("text-anchor", "middle");
  label.classList.add("node-label");
  label.textContent = truncate(node.label || node.kind, 16);
  g.appendChild(label);

  layer.appendChild(g);
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export async function selectScene(nodeId) {
  await fetch("/api/scene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId || "root" }),
  });
}
