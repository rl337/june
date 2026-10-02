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

function connect() {
  setWsState("connecting");
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => setWsState("open");
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    shell.setSnapshot(data);
    renderGraph(canvas, data, {
      onSelectNode: (id) => selectScene(id),
    });
  };
  ws.onclose = () => {
    setWsState("closed");
    setTimeout(connect, 1200);
  };
}

connect();
