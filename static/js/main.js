/** Application shell: hash router, theme toggle, sidebar drawer, status. */

import { api } from "./api.js?v=5";
import { esc } from "./ui.js?v=5";
import { routes } from "./views.js?v=5";

const view = document.getElementById("view");
const nav = document.getElementById("nav");
const sidebar = document.getElementById("sidebar");
const scrim = document.getElementById("scrim");
const menuBtn = document.getElementById("menu-btn");
const themeBtn = document.getElementById("theme-btn");

/* --- Theme ------------------------------------------------------------- */

const THEME_KEY = "maintainiq-theme";

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  themeBtn.setAttribute(
    "aria-label",
    theme === "dark" ? "Switch to light theme" : "Switch to dark theme"
  );
}

function initTheme() {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") {
    applyTheme(stored);
    return;
  }
  applyTheme("dark");
}

themeBtn.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

initTheme();

/* --- Sidebar drawer (narrow viewports) --------------------------------- */

function closeDrawer() {
  sidebar.classList.remove("is-open");
  scrim.hidden = true;
  menuBtn.setAttribute("aria-expanded", "false");
}

menuBtn.addEventListener("click", () => {
  const open = sidebar.classList.toggle("is-open");
  scrim.hidden = !open;
  menuBtn.setAttribute("aria-expanded", String(open));
});

scrim.addEventListener("click", closeDrawer);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

/* --- Router ------------------------------------------------------------ */

function currentRoute() {
  const name = window.location.hash
    .slice(1)
    .split(/[?#]/, 1)[0]
    .replace(/^\/+|\/+$/g, "");
  return Object.hasOwn(routes, name) ? name : "dashboard";
}

async function navigate() {
  const name = currentRoute();
  const route = routes[name];
  const canonicalHash = `#/${name}`;

  if (window.location.hash !== canonicalHash) {
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}${window.location.search}${canonicalHash}`
    );
  }

  for (const item of nav.querySelectorAll(".nav-item")) {
    const isActive = item.dataset.route === name;
    item.classList.toggle("is-active", isActive);
    if (isActive) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }

  document.title = `${route.title} · MaintainIQ`;
  closeDrawer();
  view.replaceChildren();
  window.scrollTo(0, 0);

  const host = document.createElement("div");
  view.appendChild(host);

  try {
    await route.render(host);
  } catch (error) {
    if (!host.isConnected) return;
    host.innerHTML = `<div class="alert alert-error"><div><strong>Something went wrong.</strong><br>${esc(
      error.message || error
    )}</div></div>`;
  }
}

window.addEventListener("hashchange", navigate);

/* --- Provider status --------------------------------------------------- */

async function loadStatus() {
  const pill = document.getElementById("provider-pill");
  const foot = document.getElementById("ai-status");

  try {
    const status = await api.status();
    const documents = `${status.indexed_documents} document(s) indexed`;
    if (status.groq_configured) {
      pill.classList.remove("is-warn");
      pill.innerHTML = '<span class="dot"></span> Groq AI connected';
      foot.textContent = `Groq key configured · ${documents}`;
    } else {
      pill.classList.add("is-warn");
      pill.innerHTML = '<span class="dot"></span> Local AI fallback';
      foot.textContent = `GROQ_API_KEY not set · ${documents}`;
    }
  } catch {
    pill.classList.add("is-warn");
    pill.innerHTML = '<span class="dot"></span> Server unreachable';
    foot.textContent = "Could not reach the API";
  }
}

loadStatus();
navigate();
