/** Chat pane wired to /api/chat + /api/models (june.chat subgraph). */

export function mountChatPanel(root = document) {
  const messagesEl = root.querySelector("#chat-messages");
  const form = root.querySelector("#chat-form");
  const input = root.querySelector("#chat-input");
  const modelEl = root.querySelector("#chat-model");
  const capsEl = root.querySelector("#chat-caps");
  const errorEl = root.querySelector("#chat-error");
  const fileEl = root.querySelector("#chat-file");
  const attachLabel = root.querySelector("#chat-attach-label");
  const sendBtn = root.querySelector("#chat-send");
  if (!messagesEl || !form || !input || !modelEl) return;

  const history = [];
  const pendingParts = [];
  const sessionId = crypto.randomUUID();

  function showError(msg) {
    if (!errorEl) return;
    errorEl.hidden = !msg;
    errorEl.textContent = msg || "";
  }

  function renderPart(part, container) {
    if (part.kind === "text" && part.text) {
      const div = document.createElement("div");
      div.textContent = part.text;
      container.appendChild(div);
    } else if (part.kind === "image" && (part.url || part.document_id)) {
      const img = document.createElement("img");
      img.src = part.url || `/api/documents/${part.document_id}`;
      img.alt = part.name || "image";
      container.appendChild(img);
    } else if (part.kind === "audio" && (part.url || part.document_id)) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = part.url || `/api/documents/${part.document_id}`;
      container.appendChild(audio);
    } else if (part.kind === "video" && (part.url || part.document_id)) {
      const video = document.createElement("video");
      video.controls = true;
      video.src = part.url || `/api/documents/${part.document_id}`;
      container.appendChild(video);
    } else if (part.document_id || part.url) {
      const a = document.createElement("a");
      a.href = part.url || `/api/documents/${part.document_id}`;
      a.textContent = part.name || "attachment";
      a.target = "_blank";
      container.appendChild(a);
    }
  }

  function addMessage(role, parts, notes) {
    const wrap = document.createElement("div");
    wrap.className = `chat-msg chat-msg--${role}`;
    const roleEl = document.createElement("div");
    roleEl.className = "chat-role";
    roleEl.textContent = role;
    wrap.appendChild(roleEl);
    (parts || []).forEach((p) => renderPart(p, wrap));
    if (notes && notes.length) {
      const n = document.createElement("div");
      n.className = "chat-notes";
      n.textContent = notes.join(" · ");
      wrap.appendChild(n);
    }
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  async function loadModels() {
    const health = await fetch("/api/health").then((r) => r.json()).catch(() => null);
    if (health && !health.junespark_configured) {
      showError("junespark.base_url not configured — set config.yaml or JUNESPARK_BASE_URL");
      return;
    }
    const res = await fetch("/api/models");
    const data = await res.json();
    if (!res.ok) {
      showError(data.detail || data.error || res.statusText);
      return;
    }
    modelEl.innerHTML = "";
    (data.models || []).forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.id;
      if (data.active && data.active.id === m.id) opt.selected = true;
      modelEl.appendChild(opt);
    });
    const active = data.active || (data.models || [])[0];
    const caps = (active && active.capabilities) || {};
    if (capsEl) {
      capsEl.textContent = `tools:${caps.tools ? "yes" : "no"} vision:${caps.vision ? "yes" : "no"}`;
    }
    if (attachLabel) attachLabel.hidden = !caps.vision;
  }

  if (fileEl) {
    fileEl.addEventListener("change", async () => {
      showError("");
      const file = fileEl.files && fileEl.files[0];
      if (!file) return;
      const body = new FormData();
      body.append("file", file);
      const res = await fetch("/api/upload", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) {
        showError(data.detail || "upload failed");
        return;
      }
      pendingParts.push(data.part);
      addMessage("user", [data.part], ["attached"]);
      fileEl.value = "";
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    const text = input.value.trim();
    if (!text && !pendingParts.length) return;
    const parts = [...pendingParts];
    if (text) parts.unshift({ kind: "text", text });
    pendingParts.length = 0;
    addMessage("user", text ? [{ kind: "text", text }] : parts);
    input.value = "";
    if (sendBtn) sendBtn.disabled = true;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          parts,
          history,
          session_id: sessionId,
          model: modelEl.value || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
      addMessage("assistant", data.parts || [{ kind: "text", text: data.text || "" }], data.notes);
      history.push({ role: "user", content: text || "[attachment]" });
      history.push({ role: "assistant", content: data.text || "" });
    } catch (err) {
      showError(String(err.message || err));
    } finally {
      if (sendBtn) sendBtn.disabled = false;
      input.focus();
    }
  });

  loadModels().catch((err) => showError(String(err.message || err)));
}
