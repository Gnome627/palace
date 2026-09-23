/* Small DOM helpers and the MDI icons (window.MDI from icons.js — path data, 24×24). */
const SVG_NS = "http://www.w3.org/2000/svg";

export const $ = (id) => document.getElementById(id);

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}

export const hasIcon = (name) => Boolean(name && window.MDI[name]);

export function icon(name) {
  const s = svg("svg", { viewBox: "0 0 24 24" });
  s.appendChild(svg("path", { d: window.MDI[name] || window.MDI.cog }));
  return s;
}

export function setIcon(target, name) { target.replaceChildren(icon(name)); }

/** Everything drawn for one card: its node on the map and its card in the list. */
export const drawnOf = (id) => document.querySelectorAll(`[data-id="${CSS.escape(id)}"]`);

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
