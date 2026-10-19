"""Browser UI regressions for the June web console (Bubble Trouble)."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.ui


def test_shell_loads_bubble_trouble_scheme(page: Page) -> None:
    root = page.locator("#june-console")
    expect(root).to_have_attribute("data-ui-scheme", "bubble-trouble")
    expect(page.locator(".scheme-mark")).to_contain_text("Bubble Trouble")
    expect(page.locator('[data-view="graph"].is-open')).to_be_visible()
    expect(page.locator('[data-view="activity"].is-open')).to_be_visible()
    expect(page.locator('[data-view="chat"].is-open')).to_be_visible()


def test_websocket_connects(page: Page) -> None:
    expect(page.locator("#ws-status")).to_have_attribute("data-state", "open", timeout=10_000)


def test_graph_renders_seeded_nodes(page: Page) -> None:
    nodes = page.locator("#canvas .graph-node")
    expect(nodes.first).to_be_visible()
    assert nodes.count() >= 4
    # Layered fan-out should include the cron root and buckets.
    ids = page.eval_on_selector_all(
        "#canvas .graph-node",
        "els => els.map(el => el.dataset.nodeId)",
    )
    assert "cron" in ids
    assert "minute" in ids


def test_zoom_controls_update_level(page: Page) -> None:
    level = page.locator("#zoom-level")
    before = level.inner_text()
    page.locator("#btn-zoom-in").click()
    expect(level).not_to_have_text(before)
    after_in = level.inner_text()
    page.locator("#btn-zoom-out").click()
    expect(level).not_to_have_text(after_in)


def test_node_click_opens_inspector(page: Page) -> None:
    # Inspector starts closed; selecting a node should open it.
    page.locator('#canvas .graph-node[data-node-id="cron"]').click()
    inspector = page.locator('[data-view="inspector"].is-open')
    expect(inspector).to_be_visible()
    expect(inspector.locator(".inspector-title")).to_contain_text("cron", ignore_case=True)
    expect(inspector.locator(".inspector-dl")).to_contain_text("role")
    expect(inspector.locator(".inspector-dl")).to_contain_text("frontier")


def test_views_menu_toggles_events_pane(page: Page) -> None:
    page.locator('.dock-top button.menu-orb[aria-label="Views"]').click()
    page.locator('.dock-top button[data-action="view:toggle:events"]').click()
    expect(page.locator('[data-view="events"].is-open')).to_be_visible()
    # Seeded events should appear in the list.
    expect(page.locator('[data-view="events"] .event-log-list li').first).to_be_visible()


def test_activity_bar_click_opens_dialog(page: Page) -> None:
    chart = page.locator('[data-view="activity"] .event-rate-chart')
    expect(chart).to_be_visible()
    bar = page.locator('[data-view="activity"] .event-rate-bar.has-events').first
    expect(bar).to_be_enabled()
    bar.click()
    dialog = page.locator("#dialog-layer .console-dialog.is-open")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Events")
    dialog.locator(".dialog-close").click()
    expect(dialog).to_have_count(0)


def test_empty_activity_bars_not_clickable(page: Page) -> None:
    empty = page.locator('[data-view="activity"] .event-rate-bar:not(.has-events)').first
    expect(empty).to_be_disabled()


def test_instance_watch_dialog(page: Page) -> None:
    # Open via console hook — avoids depending on stacked-card hit geometry.
    opened = page.evaluate(
        """async () => {
          const api = window.juneConsole;
          if (!api?.openWatch) return false;
          await api.openWatch('june.console.cron:minute:uiwatch01');
          return true;
        }"""
    )
    assert opened
    dialog = page.locator("#dialog-layer .console-dialog--graph.is-open")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".instance-watch-svg .graph-node").first).to_be_visible(
        timeout=10_000
    )
    dialog.locator(".instance-watch-svg .graph-node").first.click()
    detail = dialog.locator(".instance-watch-detail-body")
    expect(detail).to_be_visible()
    expect(detail).not_to_have_text("Loading…")
