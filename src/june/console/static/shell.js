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
        { id: "activity", label: "Event activity", action: "view:toggle:activity" },
        { id: "events", label: "Event log (list)", action: "view:toggle:events" },
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
      tip: "Activity chart and last update",
      items: [
        { id: "activity", label: "Event activity", action: "view:toggle:activity" },
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
  activity: {
    title: "Event activity",
    dock: "bottom",
    naturalWidth: null,
    naturalHeight: 160,
    defaultOpen: true,
  },
  events: {
    title: "Event log",
    dock: "left",
    naturalWidth: 340,
    naturalHeight: null,
    defaultOpen: false,
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
    /** @type {Record<string, string[]>} dock edge → stacked view ids (top is last) */
    this.dockStacks = {
      left: [],
      right: [],
      bottom: ["activity"],
      top: [],
    };
    this.lastSnapshot = null;
    this.handlers = {};
    this._buildMenus();
    this._ensureViewPanes();
    this._layoutViews();
    document.addEventListener("mousemove", (e) => this._onPointerMove(e));
  }

  _dockFor(viewId) {
    return (VIEW_SPECS[viewId] && VIEW_SPECS[viewId].dock) || "center";
  }

  _topView(dock) {
    const stack = this.dockStacks[dock] || [];
    return stack.length ? stack[stack.length - 1] : null;
  }

  _isOpen(viewId) {
    if (viewId === "graph") return true;
    const dock = this._dockFor(viewId);
    if (dock === "center") return true;
    return this._topView(dock) === viewId;
  }

  _isStacked(viewId) {
    const dock = this._dockFor(viewId);
    const stack = this.dockStacks[dock] || [];
    return stack.includes(viewId) && this._topView(dock) !== viewId;
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
    this._renderActivityChart(snapshot.event_rate || {}, snapshot.event_log || []);
    const countEl = this.workspace.querySelector('[data-view="events"] .event-count');
    if (countEl) {
      const n = (snapshot.event_log || []).length;
      countEl.textContent = String(n);
      countEl.hidden = n === 0;
    }
    const rateEl = this.workspace.querySelector('[data-view="activity"] .event-count');
    if (rateEl) {
      const bins = (snapshot.event_rate && snapshot.event_rate.bins) || [];
      const n = bins.reduce((sum, b) => sum + (b.count || 0), 0);
      rateEl.textContent = String(n);
      rateEl.hidden = n === 0;
    }
    // Keep open instance watch dialogs in sync with live pipelines.
    void this.refreshOpenWatches();
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
      list.appendChild(eventLogItem(row));
    }
    if (atBottom) {
      body.scrollTop = body.scrollHeight;
    }
  }

  _renderActivityChart(rate, eventLog) {
    const body = this.workspace.querySelector('[data-view="activity"] .view-body');
    if (!body) return;
    let chart = body.querySelector(".event-rate-chart");
    if (!chart) {
      body.innerHTML = `
        <div class="event-rate-chart" role="img" aria-label="Rolling event rate"></div>
        <p class="event-rate-hint">Click a bar for that bin’s events</p>
      `;
      chart = body.querySelector(".event-rate-chart");
    }
    const bins = rate.bins || [];
    const max = Math.max(1, ...bins.map((b) => b.count || 0));
    chart.innerHTML = "";
    bins.forEach((bin, idx) => {
      const bar = document.createElement("button");
      bar.type = "button";
      bar.className = "event-rate-bar";
      if ((bin.count || 0) > 0) bar.classList.add("has-events");
      const pct = Math.max(4, Math.round(((bin.count || 0) / max) * 100));
      bar.style.setProperty("--bar-h", `${pct}%`);
      bar.title = `${bin.count || 0} events · ${(bin.start || "").slice(11, 19)}–${(bin.end || "").slice(11, 19)}`;
      bar.dataset.binIndex = String(idx);
      bar.addEventListener("click", () => {
        this.openEventBinDialog(bin, eventLog);
      });
      chart.appendChild(bar);
    });
  }

  openEventBinDialog(bin, eventLog) {
    const indices = bin.event_indices || [];
    const rows = indices
      .map((i) => eventLog[i])
      .filter(Boolean);
    this.openCustomDialog({
      kind: `events-bin-${bin.index}`,
      title: `Events · ${(bin.start || "").slice(11, 19)}–${(bin.end || "").slice(11, 19)}`,
      bodyHtml: rows.length
        ? `<ul class="event-log-list dialog-event-list">${rows
            .map((row) => eventLogItem(row).outerHTML)
            .join("")}</ul>`
        : `<p class="dialog-text">No events in this bin.</p>`,
    });
  }

  openInstanceStackDialog(node) {
    const snap = this.lastSnapshot || {};
    const parentId = node.stack_parent_id || node.id;
    const hidden = new Set(node.stack_hidden || []);
    const all = (snap.instances || []).filter(
      (i) => i.parent_node_id === parentId || hidden.has(i.run_id),
    );
    const running = all.filter((i) => i.status === "running");
    const others = all.filter((i) => i.status !== "running");
    const ordered = [...running, ...others];
    const listHtml = ordered.length
      ? `<ul class="instance-list">${ordered
          .map((inst) => {
            const short = String(inst.run_id || "").slice(-8);
            const st = escapeHtml(inst.status || "");
            const active = escapeHtml(inst.active_node_id || "—");
            return `<li class="instance-row ${inst.status === "running" ? "is-running" : ""}">
              <button type="button" class="instance-watch" data-run-id="${escapeHtml(inst.run_id || "")}">
                <span class="instance-id">run ${escapeHtml(short)}</span>
                <span class="instance-status">${st}</span>
                <span class="instance-active">${active}</span>
              </button>
            </li>`;
          })
          .join("")}</ul>`
      : `<p class="dialog-text">No instances for this stack.</p>`;
    const dialog = this.openCustomDialog({
      kind: `stack-${parentId}`,
      title: "Running instances",
      bodyHtml: `<p class="dialog-text">Stacked instances · click a run to watch its subgraph</p>${listHtml}`,
    });
    dialog.querySelectorAll(".instance-watch").forEach((btn) => {
      btn.addEventListener("click", () => {
        const runId = btn.getAttribute("data-run-id");
        this.emit("instance:watch", { runId, parentId });
      });
    });
  }

  /**
   * Open a live subgraph viewer for a stacked instance.
   * @param {string} runId
   * @param {{ GraphViewport: typeof import('./graph.js').GraphViewport }} deps
   */
  async openInstanceWatchDialog(runId, { GraphViewport }) {
    if (!runId || !GraphViewport) return null;
    this._watchViewports = this._watchViewports || {};
    // Replace any prior watch for this run (dialog reopen).
    delete this._watchViewports[runId];
    const short = String(runId).slice(-8);
    const summary =
      (this.lastSnapshot?.instances || []).find((i) => i.run_id === runId) || {};
    const dialog = this.openCustomDialog({
      kind: `watch-${runId}`,
      title: `Watch · ${short}`,
      className: "console-dialog--graph",
      bodyHtml: `
        <p class="dialog-text instance-watch-meta">
          <span class="instance-status ${summary.status === "running" ? "is-running" : ""}">${escapeHtml(
            summary.status || "…",
          )}</span>
          · bucket ${escapeHtml(summary.bucket || "—")}
          · active <code>${escapeHtml(summary.active_node_id || "—")}</code>
        </p>
        <div class="instance-watch-layout">
          <div class="instance-watch-graph">
            <svg class="instance-watch-svg" role="img" aria-label="Instance subgraph ${escapeHtml(
              short,
            )}"></svg>
          </div>
          <aside class="instance-watch-detail" aria-live="polite">
            <h4 class="instance-watch-detail-title">Node details</h4>
            <p class="instance-watch-detail-hint">Click a node in this run’s graph.</p>
            <pre class="instance-watch-detail-body dialog-pre" hidden></pre>
          </aside>
        </div>
        <p class="event-rate-hint">Scroll to zoom · drag to pan · click a node for details</p>
      `,
    });
    const svg = dialog.querySelector(".instance-watch-svg");
    const viewport = new GraphViewport(svg, {
      onSelectNode: (nodeId) => {
        void this.showInstanceNodeDetail(runId, nodeId);
      },
    });
    this._watchViewports[runId] = {
      viewport,
      dialog,
      fitted: false,
      selectedNodeId: null,
    };
    dialog.querySelector(".dialog-close")?.addEventListener(
      "click",
      () => {
        delete this._watchViewports[runId];
      },
      { once: true },
    );
    await this.refreshInstanceWatch(runId);
    // SVG may still be 0×0 on first paint — refit after layout.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const entry = this._watchViewports?.[runId];
        if (!entry) return;
        entry.viewport.fit({ clearSelection: false });
        entry.fitted = true;
      });
    });
    return dialog;
  }

  async showInstanceNodeDetail(runId, nodeId, { quiet = false } = {}) {
    const entry = this._watchViewports?.[runId];
    if (!entry) return;
    const pane = entry.dialog.querySelector(".instance-watch-detail");
    const title = pane?.querySelector(".instance-watch-detail-title");
    const hint = pane?.querySelector(".instance-watch-detail-hint");
    const body = pane?.querySelector(".instance-watch-detail-body");
    if (!pane || !body) return;
    const id = !nodeId || nodeId === "root" ? runId : nodeId;
    entry.selectedNodeId = id;
    if (hint) hint.hidden = true;
    body.hidden = false;
    if (!quiet) {
      body.textContent = "Loading…";
      if (title) {
        const short = String(id).split(":").slice(-2).join(":");
        title.textContent = `Node · ${short}`;
      }
    }
    try {
      const res = await fetch(
        `/api/instance/${encodeURIComponent(runId)}/node/${encodeURIComponent(id)}`,
      );
      if (!res.ok) {
        if (!quiet || !body.textContent || body.textContent === "Loading…") {
          body.textContent =
            res.status === 404 ? "Node not found in this run." : "Failed to load details.";
        }
        return;
      }
      // Stale response if the user clicked another node meanwhile.
      if (entry.selectedNodeId !== id) return;
      const detail = await res.json();
      body.textContent = JSON.stringify(detail, null, 2);
      if (title && detail.node?.goal) {
        title.textContent = String(detail.node.goal);
      } else if (title && detail.kind === "instance") {
        title.textContent = `Run · ${String(runId).slice(-8)}`;
      }
    } catch {
      if (entry.selectedNodeId === id && !quiet) {
        body.textContent = "Failed to load details.";
      }
    }
  }

  async refreshInstanceWatch(runId) {
    const entry = this._watchViewports?.[runId];
    if (!entry) return;
    try {
      const res = await fetch(`/api/instance/${encodeURIComponent(runId)}/world`);
      if (!res.ok) {
        const meta = entry.dialog.querySelector(".instance-watch-meta");
        if (meta) meta.textContent = "Instance no longer available.";
        return;
      }
      const data = await res.json();
      const svg = entry.viewport.svg;
      const sized = (svg.clientWidth || 0) > 40 && (svg.clientHeight || 0) > 40;
      entry.viewport.setWorld(data.world || {}, {
        preserveCamera: Boolean(entry.fitted && sized),
      });
      if (sized) entry.fitted = true;
      const summary =
        (this.lastSnapshot?.instances || []).find((i) => i.run_id === runId) || {};
      const meta = entry.dialog.querySelector(".instance-watch-meta");
      if (meta) {
        meta.innerHTML = `
          <span class="instance-status ${summary.status === "running" ? "is-running" : ""}">${escapeHtml(
            summary.status || "…",
          )}</span>
          · bucket ${escapeHtml(summary.bucket || "—")}
          · active <code>${escapeHtml(summary.active_node_id || "—")}</code>
        `;
      }
      if (entry.selectedNodeId) {
        void this.showInstanceNodeDetail(runId, entry.selectedNodeId, { quiet: true });
      }
    } catch {
      /* ignore transient fetch errors while watching */
    }
  }

  async refreshOpenWatches() {
    const ids = Object.keys(this._watchViewports || {});
    await Promise.all(ids.map((id) => this.refreshInstanceWatch(id)));
  }

  openCustomDialog({ kind, title, bodyHtml, anchorEl = null, className = "" }) {
    for (const existing of [...this.dialogLayer.querySelectorAll(".console-dialog")]) {
      if (existing.dataset.dialog === kind) existing.remove();
    }
    const dialog = document.createElement("div");
    dialog.className = `console-dialog${className ? ` ${className}` : ""}`;
    dialog.dataset.dialog = kind;
    if (anchorEl) {
      const rect = anchorEl.getBoundingClientRect();
      dialog.style.setProperty("--origin-x", `${rect.left + rect.width / 2}px`);
      dialog.style.setProperty("--origin-y", `${rect.top + rect.height / 2}px`);
    } else {
      dialog.style.setProperty("--origin-x", "50vw");
      dialog.style.setProperty("--origin-y", "45vh");
    }
    dialog.innerHTML = `
      <button type="button" class="dialog-close" aria-label="Close">×</button>
      <h3 class="dialog-title">${escapeHtml(title)}</h3>
      ${bodyHtml}
    `;
    dialog.querySelector(".dialog-close").addEventListener("click", () => dialog.remove());
    this.dialogLayer.appendChild(dialog);
    requestAnimationFrame(() => dialog.classList.add("is-open"));
    return dialog;
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
      const countBadge =
        id === "events" || id === "activity"
          ? '<span class="event-count pill" hidden>0</span>'
          : "";
      pane.innerHTML = `
        <header class="view-chrome">
          <span class="view-title">${spec.title}</span>
          ${countBadge}
          <button type="button" class="view-close" aria-label="Close pane">×</button>
        </header>
        <div class="view-body"></div>
      `;
      pane.querySelector(".view-close").addEventListener("click", () => this.closeView(id));
      if (id === "events") {
        pane.querySelector(".view-body").innerHTML =
          '<ul class="event-log-list" aria-label="Graph event log"></ul>';
      }
      if (id === "activity") {
        pane.querySelector(".view-body").innerHTML = `
          <div class="event-rate-chart" role="img" aria-label="Rolling event rate"></div>
          <p class="event-rate-hint">Click a bar for that bin’s events</p>
        `;
      }
      if (id === "legend") {
        pane.querySelector(".view-body").innerHTML = `
          <ul class="legend-list">
            <li><span class="shape hard"></span> hard node (rect)</li>
            <li><span class="shape soft"></span> soft bubble (round-rect)</li>
            <li><span class="glow-sample">running</span> live bubble wash</li>
            <li><span class="dim-sample">dim</span> finished / trail</li>
            <li>scheme: Bubble Trouble</li>
          </ul>
        `;
      }
      this.workspace.appendChild(pane);
    }
  }

  openView(id) {
    if (id === "graph" || !VIEW_SPECS[id]) return;
    const dock = this._dockFor(id);
    if (dock === "center") return;
    const stack = this.dockStacks[dock];
    const idx = stack.indexOf(id);
    if (idx >= 0) stack.splice(idx, 1);
    stack.push(id);
    this._layoutViews();
  }

  closeView(id) {
    if (id === "graph" || !VIEW_SPECS[id]) return;
    const dock = this._dockFor(id);
    if (dock === "center") return;
    const stack = this.dockStacks[dock];
    const idx = stack.indexOf(id);
    if (idx >= 0) stack.splice(idx, 1);
    this._layoutViews();
  }

  toggleView(id) {
    if (id === "graph") return;
    const dock = this._dockFor(id);
    const stack = this.dockStacks[dock] || [];
    if (this._topView(dock) === id) {
      this.closeView(id);
    } else if (stack.includes(id)) {
      // Bring buried view to the top without discarding the stack.
      this.openView(id);
    } else {
      this.openView(id);
    }
  }

  _layoutViews() {
    const panes = [...this.workspace.querySelectorAll(".view-pane")];
    panes.forEach((pane) => {
      const id = pane.dataset.view;
      const open = this._isOpen(id);
      const stacked = this._isStacked(id);
      pane.classList.toggle("is-open", open);
      pane.classList.toggle("is-closed", !open && !stacked);
      pane.classList.toggle("is-stacked", stacked);
    });

    this.workspace.classList.remove(
      "has-left",
      "has-right",
      "has-bottom",
      "has-top",
    );
    if (this._topView("left")) this.workspace.classList.add("has-left");
    if (this._topView("right")) this.workspace.classList.add("has-right");
    if (this._topView("bottom")) this.workspace.classList.add("has-bottom");

    this._injectSeams();
  }

  _injectSeams() {
    this.workspace.querySelectorAll(".view-seam").forEach((el) => el.remove());
    if (this._topView("left")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = "events-graph";
      seam.style.gridColumn = "2";
      seam.style.gridRow = "1";
      this.workspace.appendChild(seam);
    }
    if (this._topView("right")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = "graph-status";
      seam.style.gridColumn = "4";
      seam.style.gridRow = "1";
      this.workspace.appendChild(seam);
    }
    if (this._topView("bottom")) {
      const seam = document.createElement("div");
      seam.className = "view-seam";
      seam.dataset.between = `graph-${this._topView("bottom")}`;
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

function eventLogItem(row) {
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
  return li;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
