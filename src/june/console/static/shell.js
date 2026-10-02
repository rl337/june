/** June console shell: docked menus, IDE views, expanding dialogs. */

const RETRACT_MS = 2500;
const PROXIMITY_PX = 140;

const MENU_CATALOG = {
  left: [
    {
      id: "execution",
      short: "Ex",
      name: "Execution",
      tip: "Graph run controls and scene navigation",
      items: [
        { id: "overview", label: "Overview (root scene)", action: "scene:root" },
        { id: "refresh", label: "Refresh snapshot", action: "snapshot:refresh" },
      ],
    },
    {
      id: "scene",
      short: "Sc",
      name: "Scene",
      tip: "Foreground / background layers",
      items: [
        { id: "layers", label: "Layer legend", action: "view:toggle:legend" },
      ],
    },
  ],
  top: [
    {
      id: "views",
      short: "Vi",
      name: "Views",
      tip: "Open or close workspace panes",
      items: [
        { id: "graph", label: "Graph (main)", action: "view:open:graph" },
        { id: "status", label: "Orchestrator status", action: "view:toggle:status" },
        { id: "events", label: "Event log", action: "view:toggle:events" },
        { id: "inspector", label: "Node inspector", action: "view:toggle:inspector" },
      ],
    },
  ],
  right: [
    {
      id: "run",
      short: "Ru",
      name: "Run",
      tip: "Active run metadata",
      items: [
        { id: "run-info", label: "Run details…", action: "dialog:run-details" },
      ],
    },
  ],
  bottom: [
    {
      id: "time",
      short: "Ti",
      name: "Timeline",
      tip: "Last update and event stream",
      items: [
        { id: "updated", label: "Show last update", action: "dialog:last-update" },
      ],
    },
  ],
};

const VIEW_SPECS = {
  graph: {
    title: "Graph",
    dock: "center",
    naturalWidth: null,
    naturalHeight: null,
    defaultOpen: true,
  },
  status: {
    title: "Orchestrator",
    dock: "right",
    naturalWidth: 300,
    naturalHeight: null,
    defaultOpen: false,
  },
  legend: {
    title: "Legend",
    dock: "bottom",
    naturalWidth: null,
    naturalHeight: 140,
    defaultOpen: false,
  },
  events: {
    title: "Event log",
    dock: "left",
    naturalWidth: 340,
    naturalHeight: null,
    defaultOpen: true,
  },
  inspector: {
    title: "Inspector",
    dock: "left",
    naturalWidth: 280,
    naturalHeight: null,
    defaultOpen: false,
  },
};

export class JuneConsoleShell {
  constructor(root) {
    this.root = root;
    this.workspace = root.querySelector("#view-workspace");
    this.dialogLayer = root.querySelector("#dialog-layer");
    this.orbs = [];
    this.openViews = new Set(["graph", "events"]);
    this.lastSnapshot = null;
    this.handlers = {};
    this._buildMenus();
    this._ensureViewPanes();
    this._layoutViews();
    document.addEventListener("mousemove", (e) => this._onPointerMove(e));
  }

  on(action, handler) {
    this.handlers[action] = handler;
  }

  emit(action, detail = {}) {
    if (this.handlers[action]) this.handlers[action](detail);
  }

  setSnapshot(snapshot) {
    this.lastSnapshot = snapshot;
    const sub = this.root.querySelector("#scene-title");
    const pill = this.root.querySelector("#run-status");
    const scene = snapshot.scene || {};
    if (sub) {
      sub.textContent = `${scene.scene_title || "scene"} · ${scene.scene_kind || ""}`;
    }
    if (pill) pill.textContent = snapshot.status || "idle";
    const statusBody = this.workspace.querySelector('[data-view="status"] .view-body');
    if (statusBody) {
      statusBody.textContent = JSON.stringify(snapshot.orchestrator || {}, null, 2);
    }
    const insp = this.workspace.querySelector('[data-view="inspector"] .view-body');
    if (insp) {
      insp.textContent = JSON.stringify(scene, null, 2);
    }
    this._renderEventLog(snapshot.event_log || []);
  }

  _renderEventLog(entries) {
    const body = this.workspace.querySelector('[data-view="events"] .view-body');
    if (!body) return;
    let list = body.querySelector(".event-log-list");
    if (!list) {
      body.innerHTML = '<ul class="event-log-list" aria-label="Graph event log"></ul>';
      list = body.querySelector(".event-log-list");
    }
    const atBottom = body.scrollHeight - body.scrollTop - body.clientHeight < 48;
    list.innerHTML = "";
    for (const row of entries) {
      const li = document.createElement("li");
      li.className = "event-log-row";
      if (row.type === "june.console.log") li.classList.add("is-console-log");
      if (String(row.type).includes("graph_node_start")) li.classList.add("is-start");
      if (String(row.type).includes("graph_node_end")) li.classList.add("is-end");
      li.innerHTML = `
        <span class="event-log-ts">${escapeHtml((row.ts || "").slice(11, 19))}</span>
        <span class="event-log-type">${escapeHtml(shortType(row.type))}</span>
        <span class="event-log-summary">${escapeHtml(row.summary || "")}</span>
      `;
      list.appendChild(li);
    }
    if (atBottom) {
      body.scrollTop = body.scrollHeight;
    }
  }

  _buildMenus() {
    for (const [dock, menus] of Object.entries(MENU_CATALOG)) {
      const dockEl = this.root.querySelector(`.dock-${dock}`);
      if (!dockEl) continue;
      menus.forEach((menu, index) => {
        const wrap = document.createElement("div");
        wrap.className = "menu-wrap";
        wrap.dataset.dock = dock;
        wrap.style.setProperty("--menu-index", String(index));

        const orb = document.createElement("button");
        orb.type = "button";
        orb.className = "menu-orb";
        orb.dataset.menuId = menu.id;
        orb.setAttribute("aria-label", menu.name);
        orb.setAttribute("data-tip", menu.tip);
        orb.innerHTML = `<span class="menu-orb-short">${menu.short}</span>`;
        orb.title = `${menu.name} — ${menu.tip}`;

        const expanded = document.createElement("div");
        expanded.className = "menu-expanded";
        expanded.innerHTML = `
          <div class="menu-expanded-title">${menu.name}</div>
          <p class="menu-expanded-tip">${menu.tip}</p>
          <ul class="menu-expanded-list"></ul>
        `;
        const list = expanded.querySelector(".menu-expanded-list");
        menu.items.forEach((item) => {
          const li = document.createElement("li");
          const btn = document.createElement("button");
          btn.type = "button";
          btn.textContent = item.label;
          btn.dataset.action = item.action;
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            this._handleMenuAction(item.action, orb);
          });
          li.appendChild(btn);
          list.appendChild(li);
        });

        wrap.appendChild(orb);
        wrap.appendChild(expanded);
        dockEl.appendChild(wrap);

        let retractTimer = null;
        const clearRetract = () => {
          if (retractTimer) clearTimeout(retractTimer);
          retractTimer = null;
        };
        const scheduleRetract = () => {
          clearRetract();
          retractTimer = setTimeout(() => {
            wrap.classList.remove("is-expanded");
            orb.classList.remove("is-active");
          }, RETRACT_MS);
        };

        orb.addEventListener("click", () => {
          const open = wrap.classList.toggle("is-expanded");
          orb.classList.toggle("is-active", open);
          if (open) clearRetract();
        });

        expanded.addEventListener("mouseenter", clearRetract);
        expanded.addEventListener("mouseleave", scheduleRetract);
        orb.addEventListener("mouseenter", () => {
          orb.classList.add("is-hovered");
          clearRetract();
        });
        orb.addEventListener("mouseleave", () => {
          orb.classList.remove("is-hovered");
          if (wrap.classList.contains("is-expanded")) scheduleRetract();
        });

        this.orbs.push({ orb, wrap, dock });
      });
    }
  }

  _onPointerMove(e) {
    for (const { orb, wrap } of this.orbs) {
      const r = orb.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dist = Math.hypot(e.clientX - cx, e.clientY - cy);
      const t = Math.max(0, 1 - dist / PROXIMITY_PX);
      const opacity = 0.18 + t * 0.55;
      orb.style.setProperty("--orb-opacity", String(opacity));
      if (wrap.classList.contains("is-expanded") || orb.matches(":hover")) {
        orb.style.setProperty("--orb-opacity", "1");
      }
    }
  }

  _handleMenuAction(action, anchor) {
    if (action.startsWith("view:")) {
      const parts = action.split(":");
      const verb = parts[1];
      const viewId = parts[2];
      if (verb === "open") this.openView(viewId);
      if (verb === "toggle") this.toggleView(viewId);
      return;
    }
    if (action.startsWith("dialog:")) {
      this.openDialog(action.slice(7), anchor);
      return;
    }
    this.emit(action, { anchor });
  }

  _ensureViewPanes() {
    for (const [id, spec] of Object.entries(VIEW_SPECS)) {
      if (id === "graph") continue;
      if (this.workspace.querySelector(`[data-view="${id}"]`)) continue;
      const pane = document.createElement("section");
      pane.className = "view-pane";
      pane.dataset.view = id;
      pane.dataset.dockEdge = spec.dock;
      if (spec.naturalWidth) pane.style.setProperty("--natural-w", `${spec.naturalWidth}px`);
      if (spec.naturalHeight) pane.style.setProperty("--natural-h", `${spec.naturalHeight}px`);
      pane.innerHTML = `
        <header class="view-chrome">
          <span class="view-title">${spec.title}</span>
          <button type="button" class="view-close" aria-label="Close pane">×</button>
        </header>
        <div class="view-body"></div>
      `;
      pane.querySelector(".view-close").addEventListener("click", () => this.closeView(id));
      if (id === "events") {
        pane.querySelector(".view-body").innerHTML =
          '<ul class="event-log-list" aria-label="Graph event log"></ul>';
      }
      if (id === "legend") {
        pane.querySelector(".view-body").innerHTML = `
          <ul class="legend-list">
            <li><span class="shape hard"></span> hard node (rect)</li>
            <li><span class="shape soft"></span> soft node (round-rect)</li>
            <li><span class="glow-sample">running</span> active execution</li>
            <li><span class="dim-sample">dim</span> finished / trail</li>
          </ul>
        `;
      }
      this.workspace.appendChild(pane);
    }
  }

  openView(id) {
    this.openViews.add(id);
    this._layoutViews();
  }

  closeView(id) {
    if (id === "graph") return;
    this.openViews.delete(id);
    this._layoutViews();
  }

  toggleView(id) {
    if (this.openViews.has(id)) this.closeView(id);
    else this.openView(id);
  }

  _layoutViews() {
    const leftPane =
      this.openViews.has("events")
        ? "events"
        : this.openViews.has("inspector")
          ? "inspector"
          : null;
    const panes = [...this.workspace.querySelectorAll(".view-pane")];
    panes.forEach((pane) => {
      const id = pane.dataset.view;
      let open = this.openViews.has(id);
      if (id === "events" || id === "inspector") {
        open = id === leftPane;
      }
      pane.classList.toggle("is-open", open);
      pane.classList.toggle("is-closed", !open);
    });

    this.workspace.classList.remove(
      "has-left",
      "has-right",
      "has-bottom",
      "has-top",
    );
    if (this.openViews.has("events") || this.openViews.has("inspector")) {
      this.workspace.classList.add("has-left");
    }
    if (this.openViews.has("status")) this.workspace.classList.add("has-right");
    if (this.openViews.has("legend")) this.workspace.classList.add("has-bottom");

    this._injectSeams();
  }

  _injectSeams() {
    this.workspace.querySelectorAll(".view-seam").forEach((el) => el.remove());
    if (this.openViews.has("events") || this.openViews.has("inspector")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = "events-graph";
      seam.style.gridColumn = "2";
      seam.style.gridRow = "1";
      this.workspace.appendChild(seam);
    }
    if (this.openViews.has("status")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = "graph-status";
      seam.style.gridColumn = "4";
      seam.style.gridRow = "1";
      this.workspace.appendChild(seam);
    }
    if (this.openViews.has("legend")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = "graph-legend";
      seam.style.gridColumn = "1 / 6";
      seam.style.gridRow = "2";
      this.workspace.appendChild(seam);
    }
  }

  openDialog(kind, anchorEl) {
    const existing = this.dialogLayer.querySelector(`[data-dialog="${kind}"]`);
    if (existing) {
      existing.remove();
      return;
    }
    const rect = anchorEl.getBoundingClientRect();
    const dialog = document.createElement("div");
    dialog.className = "console-dialog";
    dialog.dataset.dialog = kind;
    dialog.style.setProperty("--origin-x", `${rect.left + rect.width / 2}px`);
    dialog.style.setProperty("--origin-y", `${rect.top + rect.height / 2}px`);

    const snap = this.lastSnapshot || {};
    let body = "";
    if (kind === "run-details") {
      body = `<pre class="dialog-pre">${escapeHtml(
        JSON.stringify(
          {
            run_id: snap.run_id,
            status: snap.status,
            updated_at: snap.updated_at,
          },
          null,
          2,
        ),
      )}</pre>`;
    } else if (kind === "last-update") {
      body = `<p class="dialog-text">Last snapshot: <code>${escapeHtml(
        snap.updated_at || "—",
      )}</code></p>`;
    } else {
      body = `<p class="dialog-text">${escapeHtml(kind)}</p>`;
    }

    dialog.innerHTML = `
      <button type="button" class="dialog-close" aria-label="Close">×</button>
      <h3 class="dialog-title">${escapeHtml(kind.replace(/-/g, " "))}</h3>
      ${body}
    `;
    dialog.querySelector(".dialog-close").addEventListener("click", () => dialog.remove());
    this.dialogLayer.appendChild(dialog);
    requestAnimationFrame(() => dialog.classList.add("is-open"));
  }
}

function shortType(type) {
  const t = String(type || "");
  if (t.startsWith("core:")) return t.slice(5);
  if (t.startsWith("june.")) return t.slice(5);
  return t;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
