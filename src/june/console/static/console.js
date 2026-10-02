import { JuneConsoleShell } from "./shell.js";
import { renderGraph, selectScene } from "./graph.js";

const root = document.getElementById("june-console");
const canvas = document.getElementById("canvas");
const shell = new JuneConsoleShell(root);

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
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (msg) => {
    const data = JSON.parse(msg.data);
    shell.setSnapshot(data);
    renderGraph(canvas, data, {
      onSelectNode: (id) => selectScene(id),
    });
  };
  ws.onclose = () => setTimeout(connect, 1200);
}

connect();
