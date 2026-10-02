const canvas = document.getElementById("canvas");
const sceneTitle = document.getElementById("scene-title");
const runStatus = document.getElementById("run-status");
const runId = document.getElementById("run-id");
const updatedAt = document.getElementById("updated-at");
const btnRoot = document.getElementById("btn-root");

const NODE_W = 132;
const NODE_H = 44;
const LAYER_Y = { foreground: 110, background: 220 };

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    render(data);
  };
  ws.onclose = () => setTimeout(connect, 1200);
}

function render(snapshot) {
  const scene = snapshot.scene || {};
  sceneTitle.textContent = `${scene.scene_title || "scene"} · ${scene.scene_kind || ""}`;
  runStatus.textContent = snapshot.status || "idle";
  runId.textContent = snapshot.run_id ? `run ${snapshot.run_id}` : "";
  updatedAt.textContent = snapshot.updated_at || "";

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

  nodes.forEach((n) => drawNode(nodeLayer, n, positions.get(n.id)));
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
  line.setAttribute("x1", a.x + NODE_W / 2);
  line.setAttribute("y1", a.y + NODE_H);
  line.setAttribute("x2", b.x + NODE_W / 2);
  line.setAttribute("y2", b.y);
  line.setAttribute("stroke", "#4b5c78");
  line.setAttribute("stroke-width", "1.5");
  layer.appendChild(line);
}

function drawNode(layer, node, pos) {
  if (!pos) return;
  const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
  g.classList.add("node", node.execution || "pending");
  g.style.cursor = node.layer === "foreground" ? "pointer" : "default";
  if (node.layer === "foreground") {
    g.addEventListener("click", () => selectScene(node.id));
  }

  const fill = node.shape === "round_rect" ? "#7c5cbf" : "#3d6fb8";
  let shape;
  if (node.shape === "round_rect") {
    shape = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    shape.setAttribute("rx", "14");
    shape.setAttribute("ry", "14");
  } else {
    shape = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  }
  shape.setAttribute("x", pos.x);
  shape.setAttribute("y", pos.y);
  shape.setAttribute("width", NODE_W);
  shape.setAttribute("height", NODE_H);
  shape.setAttribute("fill", fill);
  shape.setAttribute("stroke", "#dfe7f5");
  shape.setAttribute("stroke-width", "1");
  if (node.execution === "running") {
    shape.setAttribute("filter", "url(#glow)");
  }
  g.appendChild(shape);

  const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
  label.setAttribute("x", pos.x + NODE_W / 2);
  label.setAttribute("y", pos.y + NODE_H / 2 + 4);
  label.setAttribute("text-anchor", "middle");
  label.classList.add("node-label");
  label.textContent = truncate(node.label || node.kind, 16);
  g.appendChild(label);

  layer.appendChild(g);
}

function truncate(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

async function selectScene(nodeId) {
  await fetch("/api/scene", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ node_id: nodeId || "root" }),
  });
}

btnRoot.addEventListener("click", () => selectScene("root"));
connect();
