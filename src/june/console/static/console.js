import { JuneConsoleShell } from "./shell.js";
import { GraphViewport, selectScene } from "./graph.js";

const root = document.getElementById("june-console");
const canvas = document.getElementById("canvas");
const wsStatus = document.getElementById("ws-status");
const shell = new JuneConsoleShell(root);

const viewport = new GraphViewport(canvas, {
  onSelectNode: (id) => {
    selectScene(id);
    const sub = document.getElementById("scene-title");
    if (sub && id && id !== "root") {
      sub.dataset.selected = id;
    }
  },
  onStackBadge: (node) => {
    shell.openInstanceStackDialog(node);
  },
});

shell.on("instance:watch", ({ runId }) => {
  if (!runId) return;
  // Prefer the dedicated subgraph watch dialog; also center main view if present.
  void shell.openInstanceWatchDialog(runId, { GraphViewport });
  if (viewport._index?.has(runId)) {
    viewport.select(runId, { zoomToward: true });
  }
});

document.getElementById("btn-zoom-in")?.addEventListener("click", () => viewport.zoomIn());
document.getElementById("btn-zoom-out")?.addEventListener("click", () => viewport.zoomOut());
document.getElementById("btn-zoom-fit")?.addEventListener("click", () => viewport.fit());
document.getElementById("btn-zoom-focus")?.addEventListener("click", () => viewport.focusSelected());

function setWsState(state) {
  if (!wsStatus) return;
  wsStatus.dataset.state = state;
  wsStatus.title = state === "open" ? "Live (WebSocket connected)" : "Reconnecting…";
}

shell.on("scene:root", () => {
  viewport.clearSelection();
  viewport.fit();
  selectScene("root");
});
shell.on("snapshot:refresh", async () => {
  const res = await fetch("/api/snapshot");
  applySnapshot(await res.json());
});

function applySnapshot(data) {
  shell.setSnapshot(data);
  viewport.setWorld(data.world || { nodes: [], edges: [], width: 400, height: 240 }, {
    preserveCamera: true,
  });
}

let pollTimer = null;
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/snapshot");
      applySnapshot(await res.json());
    } catch {
      /* ignore transient poll errors */
    }
  }, 1000);
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

function connect() {
  setWsState("connecting");
  startPolling();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    setWsState("open");
    stopPolling();
  };
  ws.onmessage = (msg) => {
    applySnapshot(JSON.parse(msg.data));
  };
  ws.onclose = () => {
    setWsState("closed");
    startPolling();
    setTimeout(connect, 1200);
  };
}

connect();

// Lightweight console hooks for watch dialogs / manual debugging.
window.juneConsole = {
  shell,
  viewport,
  openWatch: (runId) => shell.openInstanceWatchDialog(runId, { GraphViewport }),
};
