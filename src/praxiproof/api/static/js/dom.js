// DOM handles, page state, and the small string/format helpers every view needs.
const $ = (sel, el = document) => el.querySelector(sel);
const view = $("#view");
const state = { query: "", pollTimer: null, renderToken: 0 };

// Manual text is quoted as written; drop the list marker it was copied with.
const plain = (text) => String(text ?? "").replace(/^\s*(?:[-*+]|\d+\.)\s+/, "");
const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 3500);
}

const fmtTime = (s) => {
  if (s == null) return "-";
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, "0")}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
};
const fmtDuration = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.round(s % 60)).padStart(2, "0")}`;
const locale = () => (LANG === "zh" ? "zh-CN" : "en-US");
const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleString(locale(), { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "-";
const fmtBytes = (n) => (n == null ? "" : n > 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.round(n / 1e3)} KB`);
const busy = (status) => status === "queued" || status === "processing";
const matches = (row) => !state.query || JSON.stringify(row).toLowerCase().includes(state.query);

// Thrown by rapi() and caught in render(): a page renderer that lost a race with navigation gives up quietly.
const STALE = Symbol("stale render");
