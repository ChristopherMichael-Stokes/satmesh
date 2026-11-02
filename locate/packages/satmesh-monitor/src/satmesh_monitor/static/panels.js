import { VIRIDIS_CSS_GRADIENT } from "./colour.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const SECONDS_PER_MINUTE = 60;
const STRIP = { width: 640, height: 150, left: 52, right: 12, top: 10, bottom: 26 };

export function formatClock(seconds) {
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / SECONDS_PER_MINUTE);
  const rest = String(whole % SECONDS_PER_MINUTE).padStart(2, "0");
  return `${minutes}:${rest}`;
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svgElement(tag, attributes) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

function intervalText(label, interval, unit) {
  return interval ? `${label} ${interval.centre} ± ${interval.half_width} ${unit}` : `${label} any`;
}

export function renderPriors(container, priors) {
  const position = priors.position
    ? `position ${priors.position.east_m.toFixed(0)}, ${priors.position.north_m.toFixed(0)} m, radius ${priors.position.radius_m.toFixed(0)} m`
    : "position anywhere in the area";
  const lines = [
    position,
    intervalText("heading", priors.heading_deg, "°"),
    intervalText("pitch", priors.pitch_deg, "°"),
    intervalText("height", priors.height_m, "m"),
  ];
  container.replaceChildren(...lines.map((line) => element("li", "", line)));
}

export function renderProgress(container, state) {
  const rows = state.stages.map((stage) => {
    const running = stage.endS === null;
    const elapsed = (running ? state.timeS : stage.endS) - stage.startS;
    const row = element("li", running ? "stage running" : "stage done");
    row.append(
      element("span", "stage-name", stage.stage),
      element("span", "stage-units", `${stage.units.toLocaleString()} units`),
      element("span", "stage-time", `${formatClock(stage.startS)} → ${running ? "…" : formatClock(stage.endS)}  (${formatClock(elapsed)})`),
    );
    return row;
  });
  container.replaceChildren(...rows);
}

export function renderLegend(container, range) {
  const bar = element("div", "legend-bar");
  bar.style.background = VIRIDIS_CSS_GRADIENT;
  const labels = element("div", "legend-labels");
  labels.append(
    element("span", "", range ? range.low.toFixed(3) : "–"),
    element("span", "", "similarity"),
    element("span", "", range ? range.high.toFixed(3) : "–"),
  );
  const rendered = element("div", "legend-rendered");
  rendered.append(element("span", "swatch rendered"), element("span", "", "rendered, not yet described"));
  container.replaceChildren(bar, labels, rendered);
}

function logTicks(low, high) {
  const ticks = [];
  for (let exponent = Math.ceil(Math.log10(low)); 10 ** exponent <= high; exponent += 1) ticks.push(10 ** exponent);
  return ticks;
}

// Spread of the candidates against time on a log axis; the full series is faint, the part up to the cursor solid.
export function renderConvergence(svg, fullSeries, state, durationS) {
  svg.setAttribute("viewBox", `0 0 ${STRIP.width} ${STRIP.height}`);
  const usable = fullSeries.filter((p) => p.spreadM > 0);
  if (usable.length === 0) {
    svg.replaceChildren(svgElement("text", { x: STRIP.left, y: STRIP.height / 2, class: "axis-text" }));
    svg.firstChild.textContent = "no candidates with a spread yet";
    return;
  }
  const spreads = usable.map((p) => p.spreadM);
  const low = 10 ** Math.floor(Math.log10(Math.min(...spreads)));
  const high = 10 ** Math.ceil(Math.log10(Math.max(...spreads)) + 1e-9);
  const spanLog = Math.max(Math.log10(high / low), 1);
  const plotWidth = STRIP.width - STRIP.left - STRIP.right;
  const plotHeight = STRIP.height - STRIP.top - STRIP.bottom;
  const x = (timeS) => STRIP.left + (durationS > 0 ? (timeS / durationS) * plotWidth : 0);
  const y = (metres) => STRIP.top + plotHeight * (1 - Math.log10(metres / low) / spanLog);

  const nodes = [];
  for (const tick of logTicks(low, low * 10 ** spanLog)) {
    nodes.push(svgElement("line", { x1: STRIP.left, x2: STRIP.width - STRIP.right, y1: y(tick), y2: y(tick), class: "grid" }));
    const label = svgElement("text", { x: STRIP.left - 6, y: y(tick) + 4, class: "axis-text", "text-anchor": "end" });
    label.textContent = tick >= 1000 ? `${tick / 1000} km` : `${tick} m`;
    nodes.push(label);
  }
  const path = (series) => series.map((p, i) => `${i === 0 ? "M" : "L"}${x(p.timeS).toFixed(1)},${y(p.spreadM).toFixed(1)}`).join(" ");
  nodes.push(svgElement("path", { d: path(usable), class: "series future" }));
  const seen = usable.filter((p) => p.timeS <= state.timeS);
  nodes.push(svgElement("path", { d: path(seen), class: "series seen" }));
  for (const p of seen) nodes.push(svgElement("circle", { cx: x(p.timeS), cy: y(p.spreadM), r: 3, class: "dot" }));
  nodes.push(svgElement("line", { x1: x(state.timeS), x2: x(state.timeS), y1: STRIP.top, y2: STRIP.top + plotHeight, class: "cursor" }));
  const caption = svgElement("text", { x: STRIP.left, y: STRIP.height - 6, class: "axis-text" });
  caption.textContent = `candidate spread (RMS from centroid), 0 – ${formatClock(durationS)}`;
  nodes.push(caption);
  svg.replaceChildren(...nodes);
}
