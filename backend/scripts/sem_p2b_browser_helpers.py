"""Shared CDP helpers for Phase 2B browser harness scripts."""

from __future__ import annotations

import json
import time

SET_VALUE = """
function setNativeValue(el, value) {
  if (!el) return false;
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}
"""


def select_model_by_needle(
    val,
    wait_true,
    needle: str,
    *,
    model_id: str | None = None,
    allow_api_only: bool = False,
) -> bool:
    val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(0.25)
    mid_expr = json.dumps(model_id) if model_id else "null"
    needle_expr = json.dumps(needle)
    val(
        SET_VALUE
        + f"""
    (() => {{
      const trigger = document.querySelector('[data-testid=\"semantic-model-combobox-trigger\"]')
        || document.querySelector('[role=\"combobox\"]');
      trigger?.click();
      const inp = document.querySelector('[data-testid=\"semantic-model-combobox-search\"]')
        || document.querySelector('input[placeholder=\"Search semantic models…\"]');
      setNativeValue(inp, {needle_expr});
      return true;
    }})()
    """
    )
    wait_true(
        f"""
        (() => {{
          const buttons = [...document.querySelectorAll('[data-testid=\"semantic-model-combobox-list\"] button')];
          return buttons.some(b => ({mid_expr} && b.getAttribute('data-model-id') === {mid_expr})
            || b.textContent?.includes({needle_expr}));
        }})()
        """,
        20,
    )
    val(
        f"""
        (() => {{
          const buttons = [...document.querySelectorAll('[data-testid=\"semantic-model-combobox-list\"] button')];
          let btn = null;
          if ({mid_expr}) {{
            btn = buttons.find(b => b.getAttribute('data-model-id') === {mid_expr});
          }}
          if (!btn) {{
            btn = buttons.find(b => b.textContent?.includes({needle_expr}));
          }}
          btn?.click();
          return !!btn;
        }})()
        """
    )
    time.sleep(2.0)
    wait_true('!document.body.innerText.includes("Loading semantic layer")', 45)
    selected = wait_true(
        f"""
        (() => {{
          const root = document.querySelector('[data-testid=\"semantic-model-combobox-trigger\"]')
            || document.querySelector('[role=\"combobox\"]');
          const text = root?.innerText || '';
          return text.includes({needle_expr});
        }})()
        """,
        25,
    )
    if selected or not allow_api_only:
        return selected
    return wait_true(
        f"""
        (async () => {{
          try {{
            const r = await fetch('/api/v1/semantic/models?search=' + encodeURIComponent({needle_expr}));
            const j = await r.json();
            return (j.models || []).some(m => m.name?.includes({needle_expr}) || m.key?.includes({needle_expr}));
          }} catch {{ return false; }}
        }})()
        """,
        15,
    )


def navigate_to_model(send, val, wait_true, base_url: str, model_id: str) -> bool:
    send("Page.navigate", {"url": f"{base_url}/semantic-layer?model={model_id}"})
    time.sleep(2.5)
    if not wait_true('!!document.querySelector(\'[data-testid=\"semantic-create-model\"]\')', 120):
        return False
    wait_true('!document.body.innerText.includes("Loading semantic layer")', 90)
    return wait_true(
        """
        (() => {
          const btn = document.querySelector('[data-testid=\"semantic-model-combobox-trigger\"]');
          const label = btn?.innerText || '';
          return label.length > 0 && !label.includes('Select semantic model');
        })()
        """,
        20,
    )


def open_advanced_tab(val, testid: str, fallback_label: str) -> None:
    val("document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))")
    time.sleep(0.2)
    val("document.querySelector('[data-testid=\"semantic-advanced-trigger\"]')?.click()")
    time.sleep(0.35)
    val(
        f"""
        (() => {{
          const byId = document.querySelector('[data-testid=\"{testid}\"]');
          if (byId) {{ byId.click(); return true; }}
          const item = [...document.querySelectorAll('[role=\"menuitem\"]')].find(x =>
            x.textContent?.includes({json.dumps(fallback_label)}));
          item?.click();
          return !!item;
        }})()
        """
    )
    time.sleep(1.2)
