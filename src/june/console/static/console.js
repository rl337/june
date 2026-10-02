import { JuneConsoleShell } from "./shell.js";
import { renderGraph, selectScene } from "./graph.js";

const root = document.getElementById("june-console");
const canvas = document.getElementById("canvas");
const wsStatus = document.getElementById("ws-status");
const shell = new JuneConsoleShell(root);

function setWsState(state) {
  if (!wsStatus) return;
  wsStatus.dataset.state = state;
  wsStatus.title = state === "open" ? "Live (WebSocket connected)" : "Reconnecting…";
}

shell.on("scene:root", () => selectScene("root"));
shell.on("snapshot:refresh", async () => {
  const res = await fetch("/api/snapshot");
  const data = await res.json();
  shell.setSnapshot(data);
  renderGraph(canvas, data, {
    onSelectNode: (id) => selectScene(id),
  });
});

function applySnapshot(data) {
  shell.setSnapshot(data);
  renderGraph(canvas, data, {
    onSelectNode: (id) => selectScene(id),
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
