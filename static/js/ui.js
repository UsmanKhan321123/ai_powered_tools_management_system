/**
 * Shared UI primitives: escaping, toasts, modals, tables, chips, charts.
 * Everything renders to HTML strings or DOM nodes so views stay declarative.
 */

/* --- Escaping --------------------------------------------------------- */

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape untrusted text before interpolating it into markup. */
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
}

export function attr(value) {
  return esc(value);
}

/* --- Icons ------------------------------------------------------------ */

const svg = (body, extra = "") =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"${extra}>${body}</svg>`;

export const ICON = {
  check: svg('<path d="M20 6.5L9.4 17.1 4 11.7"/>'),
  alert: svg('<path d="M12 9v4.5M12 17h.01"/><path d="M10.3 3.9L2.6 17.2A2 2 0 004.3 20.2h15.4a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>'),
  info: svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.8h.01"/>'),
  close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
  plus: svg('<path d="M12 5v14M5 12h14"/>'),
  upload: svg('<path d="M12 16V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V15"/>'),
  sparkles: svg('<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>'),
  search: svg('<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>'),
  download: svg('<path d="M12 4v12M7.5 11.5L12 16l4.5-4.5"/><path d="M4 19h16"/>'),
  wrench: svg('<path d="M14.7 6.3a4.5 4.5 0 105.9 5.9l-9 9a2.4 2.4 0 01-3.4-3.4l9-9z"/>'),
  inbox: svg('<path d="M3.5 12.5l2.4-7A2 2 0 017.8 4h8.4a2 2 0 011.9 1.5l2.4 7"/><path d="M3.5 12.5h4.2l1.2 2.6h6.2l1.2-2.6h4.2v5a2 2 0 01-2 2h-13a2 2 0 01-2-2z"/>'),
  chevron: svg('<path d="M6 9.5l6 6 6-6"/>'),
  clock: svg('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 1.8"/>'),
  shield: svg('<path d="M12 3l7 3v5.5c0 4.3-2.9 8.2-7 9.5-4.1-1.3-7-5.2-7-9.5V6z"/><path d="M9.2 12l2 2 3.6-3.9"/>'),
  box: svg('<path d="M12 2.8l8 4.4v9.6l-8 4.4-8-4.4V7.2z"/><path d="M4.3 7.3L12 11.7l7.7-4.4M12 11.7V21"/>'),
  clipboard: svg('<rect x="5" y="4.5" width="14" height="16" rx="2.2"/><path d="M9 4.5a3 3 0 016 0M9 11h6M9 15h4"/>'),
  gauge: svg('<path d="M4 18a8 8 0 1116 0"/><path d="M12 18l4-5"/>'),
};

/** Icon name used in the `.stat-label` rows. */
export const STAT_ICONS = {
  equipment: ICON.box,
  open: ICON.clipboard,
  done: ICON.check,
  reported: ICON.alert,
};

/* --- Small formatters -------------------------------------------------- */

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString(undefined, {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export function truncate(value, max = 70) {
  const text = String(value ?? "");
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Animate a stat tile from 0 to `target`. */
export function countUp(node, target, duration = 650) {
  const end = Number(target) || 0;
  if (prefersReducedMotion() || end === 0) {
    node.textContent = String(end);
    return;
  }
  const started = performance.now();
  const step = (now) => {
    const progress = Math.min(1, (now - started) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = String(Math.round(end * eased));
    if (progress < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* --- Chips ------------------------------------------------------------- */

const PRIORITY_TONE = { Critical: "red", High: "amber", Medium: "brand", Low: "neutral" };
const STATUS_TONE = {
  Open: "brand",
  "In Progress": "amber",
  "On Hold": "neutral",
  Closed: "mint",
};
const HEALTH_TONE = { Operational: "mint", "Needs Attention": "amber", Offline: "red" };

export function priorityChip(priority) {
  const tone = PRIORITY_TONE[priority] || "neutral";
  return `<span class="chip chip-${tone}">${esc(priority || "—")}</span>`;
}

export function statusChip(status) {
  const tone = STATUS_TONE[status] || "neutral";
  return `<span class="chip chip-${tone}">${esc(status || "—")}</span>`;
}

export function healthChip(status) {
  const tone = HEALTH_TONE[status] || "neutral";
  return `<span class="chip chip-${tone}">${esc(status || "—")}</span>`;
}

export function neutralChip(text) {
  return `<span class="chip chip-neutral chip-plain">${esc(text)}</span>`;
}

/* --- Layout fragments -------------------------------------------------- */

export function pageIntro({ eyebrow, title, subtitle, badge }) {
  return `
    <div class="page-intro">
      <div>
        <div class="eyebrow">${esc(eyebrow)}</div>
        <h1 class="page-title">${esc(title)}</h1>
        <div class="page-sub">${esc(subtitle)}</div>
      </div>
      ${badge ? `<div class="badge">✦ &nbsp;${esc(badge)}</div>` : ""}
    </div>`;
}

export function sectionHead(title, note = "", action = "") {
  return `
    <div class="section-head"><h2 class="section-title">${esc(title)}</h2>${action}</div>
    ${note ? `<div class="section-note">${esc(note)}</div>` : ""}`;
}

export function alertBox(type, html) {
  const icon = type === "success" ? ICON.check
    : type === "error" ? ICON.alert
    : type === "warn" ? ICON.shield
    : ICON.info;
  return `<div class="alert alert-${type}">${icon}<div>${html}</div></div>`;
}

export function emptyState(title, hint = "") {
  return `
    <div class="empty">
      ${ICON.inbox}
      <strong>${esc(title)}</strong>
      ${hint ? `<span>${esc(hint)}</span>` : ""}
    </div>`;
}

export function skeletonCard(lines = 4) {
  const rows = Array.from({ length: lines })
    .map(() => '<div class="skeleton skeleton-line"></div>')
    .join("");
  return `<div class="card"><div class="skeleton skeleton-line" style="width:38%;height:17px"></div>${rows}</div>`;
}

export function table(columns, rows, { emptyTitle = "Nothing to show yet", emptyHint = "", rowClass = "" } = {}) {
  if (!rows || rows.length === 0) return emptyState(emptyTitle, emptyHint);
  const head = columns.map((column) => `<th>${esc(column.label)}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((column) => {
          const value = column.render ? column.render(row) : esc(row[column.key]);
          return `<td class="${column.className || ""}">${value}</td>`;
        })
        .join("");
      const cls = typeof rowClass === "function" ? rowClass(row) : rowClass;
      return `<tr${cls ? ` class="${cls}"` : ""}>${cells}</tr>`;
    })
    .join("");
  return `<div class="table-wrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

/* --- Charts ------------------------------------------------------------ */

const DONUT_COLORS = {
  Operational: "#13b89a",
  "Needs Attention": "#e08a2b",
  Offline: "#dc5148",
};

/**
 * Render a donut chart with a centred total and a legend.
 * segments: [{ label, value }]
 */
export function donut(segments, { caption = "Assets", palette = DONUT_COLORS } = {}) {
  const visible = segments.filter((segment) => segment.value > 0);
  const total = visible.reduce((sum, segment) => sum + segment.value, 0);
  const radius = 70;
  const circumference = 2 * Math.PI * radius;
  const gap = visible.length > 1 ? 3 : 0;

  let offset = 0;
  const arcs = visible
    .map((segment) => {
      const length = (segment.value / total) * circumference;
      const arc = `<circle cx="90" cy="90" r="${radius}" stroke="${palette[segment.label] || "#4968e8"}"
        stroke-width="18" stroke-dasharray="${Math.max(length - gap, 0.5)} ${circumference}"
        stroke-dashoffset="${-offset}"><title>${esc(segment.label)}: ${segment.value}</title></circle>`;
      offset += length;
      return arc;
    })
    .join("");

  const legend = visible
    .map(
      (segment) => `
      <span class="legend-item">
        <span class="legend-swatch" style="background:${palette[segment.label] || "#4968e8"}"></span>
        ${esc(segment.label)}
        <span class="legend-value">${segment.value}</span>
      </span>`
    )
    .join("");

  return `
    <div class="chart-donut">
      <div class="donut">
        <svg viewBox="0 0 180 180" role="img" aria-label="${esc(caption)} by status: ${visible
          .map((segment) => `${segment.label} ${segment.value}`)
          .join(", ")}">
          <circle class="donut-track" cx="90" cy="90" r="${radius}" stroke-width="18"/>
          ${arcs}
        </svg>
        <div class="donut-center">
          <div>
            <div class="donut-total">${total}</div>
            <div class="donut-caption">${esc(caption)}</div>
          </div>
        </div>
      </div>
      <div class="legend">${legend}</div>
    </div>`;
}

/**
 * Render a horizontal bar chart.
 * items: [{ label, value, caption? }]
 */
export function bars(items, { emptyTitle = "Nothing to show yet" } = {}) {
  if (!items || items.length === 0) return emptyState(emptyTitle);
  const max = Math.max(...items.map((item) => item.value), 1);
  const rows = items
    .map(
      (item) => `
      <div class="bar-row">
        <span class="bar-label" title="${attr(item.label)}">${esc(item.label)}</span>
        <span class="bar-track"><span class="bar-fill" style="width:${Math.max((item.value / max) * 100, 3).toFixed(1)}%"></span></span>
        <span class="bar-value">${item.value}${item.caption ? ` <span class="muted">${esc(item.caption)}</span>` : ""}</span>
      </div>`
    )
    .join("");
  return `<div class="bars">${rows}</div>`;
}

/* --- Toasts ------------------------------------------------------------ */

export function toast(message, { title = "", type = "info", timeout } = {}) {
  const host = document.getElementById("toasts");
  if (!host) return () => {};
  const icon = type === "success" ? ICON.check : type === "error" ? ICON.alert : ICON.info;
  const node = document.createElement("div");
  node.className = `toast toast-${type}`;
  node.innerHTML = `${icon}<div>${title ? `<strong>${esc(title)}</strong>` : ""}${esc(message)}</div>`;
  host.appendChild(node);

  const remove = () => {
    if (!node.isConnected) return;
    node.classList.add("is-leaving");
    setTimeout(() => node.remove(), 200);
  };
  setTimeout(remove, timeout ?? (type === "error" ? 9000 : 4500));
  return remove;
}

/* --- Modal ------------------------------------------------------------- */

/**
 * Open a modal containing a form. `onSubmit(form)` may return a promise; the
 * modal closes only when it resolves without throwing.
 */
export function openModal({ title, subtitle = "", body, submitLabel = "Save", onSubmit }) {
  const root = document.getElementById("modal-root");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true" aria-label="${attr(title)}">
      <form novalidate>
        <div class="modal-head">
          <div>
            <h2>${esc(title)}</h2>
            ${subtitle ? `<p>${esc(subtitle)}</p>` : ""}
          </div>
          <button class="icon-btn" type="button" data-close aria-label="Close">${ICON.close}</button>
        </div>
        <div class="modal-body">${body}</div>
        <div class="modal-foot">
          <button class="btn" type="button" data-close>Cancel</button>
          <button class="btn btn-primary" type="submit">${esc(submitLabel)}</button>
        </div>
      </form>
    </div>`;

  const close = () => {
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };

  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop || event.target.closest("[data-close]")) close();
  });
  document.addEventListener("keydown", onKey);

  const form = backdrop.querySelector("form");
  const submit = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    try {
      await onSubmit(form);
      close();
    } catch (error) {
      toast(error.message || "Something went wrong.", { type: "error", title: "Not saved" });
    } finally {
      submit.disabled = false;
    }
  });

  root.appendChild(backdrop);
  const firstField = form.querySelector("input, select, textarea");
  if (firstField) firstField.focus();
  return { close, form };
}

/** Read a form into a plain object, trimming text values. */
export function formValues(form) {
  const values = {};
  for (const [key, value] of new FormData(form).entries()) {
    values[key] = typeof value === "string" ? value.trim() : value;
  }
  return values;
}

/** Toggle a button between idle and busy states without losing its label. */
export async function withBusy(button, task, busyLabel = "Working…") {
  if (!button) return task();
  const original = button.innerHTML;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await task();
  } finally {
    button.disabled = false;
    button.innerHTML = original;
  }
}

/** Delegated click helper: `on(root, "[data-x]", handler)`. */
export function delegate(root, selector, handler) {
  root.addEventListener("click", (event) => {
    const match = event.target.closest(selector);
    if (match && root.contains(match)) handler(match, event);
  });
}
