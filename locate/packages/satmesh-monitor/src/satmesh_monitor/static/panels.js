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

const SCORE_DECIMALS = 3;
const OFFSET_DECIMALS = 1;
const MISSING = "–";

function signed(degrees) {
  return `${degrees >= 0 ? "+" : "−"}${Math.abs(degrees).toFixed(OFFSET_DECIMALS)}°`;
}

function scoreCell(value) {
  return element("td", "num", value === null ? MISSING : value.toFixed(SCORE_DECIMALS));
}

// The fused window: each frame with its heading offset from the first, then one row per level 1 place
// whose cells are the frames' similarities and whose last cell is their sum (the score ranked on).
export function renderFusion(container, state, photoUrl) {
  const window = state.fusion;
  if (!window) {
    container.replaceChildren(element("p", "muted", "no frames fused"));
    return;
  }
  const strip = element("div", "fusion-frames");
  for (const [index, frame] of window.frames.entries()) {
    const figure = element("figure", "fusion-frame");
    const image = element("img");
    image.src = photoUrl(frame.photo);
    image.alt = frame.photo;
    figure.append(
      image,
      element("figcaption", "", `${index + 1}  ${signed(frame.yaw_offset_deg)}  (lattice ${signed(frame.lattice_offset_deg)})`),
    );
    strip.append(figure);
  }
  const places = state.candidates.get(1) ?? [];
  const table = element("table", "fusion-scores");
  const head = element("tr");
  head.append(element("th", "", "place"), ...window.frames.map((_, i) => element("th", "num", `f${i + 1}`)), element("th", "num", "sum"));
  table.append(head);
  for (const place of places) {
    const row = element("tr");
    row.append(
      element("th", "", `#${place.rank} ${place.heading_deg.toFixed(0)}°`),
      ...(place.frame_similarities ?? window.frames.map(() => null)).map(scoreCell),
      element("td", "num total", place.similarity.toFixed(SCORE_DECIMALS)),
    );
    table.append(row);
  }
  const note = element("p", "muted", "frame i is scored at the place's heading plus its offset; the sum ranks the places");
  container.replaceChildren(strip, places.length ? table : element("p", "muted", "level 1 not ranked yet"), note);
}

function priorsLine(priors) {
  const parts = [];
  if (priors.position) parts.push(`area r ${priors.position.radius_m.toFixed(0)} m`);
  if (priors.heading_deg) parts.push(`heading ${priors.heading_deg.centre} ± ${priors.heading_deg.half_width}°`);
  if (priors.pitch_deg) parts.push(`pitch ${priors.pitch_deg.centre} ± ${priors.pitch_deg.half_width}°`);
  if (priors.height_m) parts.push(`height ${priors.height_m.centre} ± ${priors.height_m.half_width} m`);
  return parts.length ? parts.join(", ") : "no priors";
}

function verdictText(rank, result) {
  const detail = result.status === "running" ? "checking…" : `${result.framesTracked}/${result.framesTotal} tracked, ${result.inliers} inliers`;
  return `#${rank} ${result.status}: ${detail}`;
}

// One block per pass of the search: the priors it ran with, what it found, how its places verified,
// and the widening that followed.
export function renderLadder(container, state) {
  const blocks = state.passes.map((pass) => {
    const block = element("li", "pass");
    const finished = pass.endS !== null;
    block.append(element("div", "pass-title", `pass ${pass.index}  ${formatClock(pass.startS)}${finished ? ` → ${formatClock(pass.endS)}` : " → …"}`));
    block.append(element("div", "muted", priorsLine(pass.priors)));
    const coarse = pass.candidates.get(1);
    const fine = pass.candidates.get(2);
    if (coarse) block.append(element("div", "", `level 1: best place ${coarse[0].similarity.toFixed(SCORE_DECIMALS)} at ${coarse[0].east_m.toFixed(0)}, ${coarse[0].north_m.toFixed(0)} m`));
    if (fine) block.append(element("div", "", `level 2: ${fine.length} places, best ${fine[0].similarity.toFixed(SCORE_DECIMALS)}`));
    for (const [rank, result] of [...pass.verification.entries()].sort((a, b) => a[0] - b[0])) {
      block.append(element("div", `verdict ${result.status}`, verdictText(rank, result)));
    }
    if (pass.relaxation) {
      const r = pass.relaxation;
      const unit = r.prior === "heading" || r.prior === "pitch" ? "°" : " m";
      block.append(element("div", "relaxed", `nothing verified: ${r.prior} widened ${r.half_width_before}${unit} → ${r.half_width_after}${unit}`));
    }
    return block;
  });
  if (state.fix) {
    const last = blocks[blocks.length - 1];
    last?.append(element("div", "verdict accepted", `fix: ${state.fix.east_m.toFixed(0)}, ${state.fix.north_m.toFixed(0)} m, heading ${state.fix.heading_deg.toFixed(0)}°, ${state.fix.inliers} inliers`));
  }
  container.replaceChildren(...blocks);
}

const STEP_TEXT = {
  "yaw offsets": "XFeat features are matched between the fused frames; each pair's rotation becomes a heading change about the vertical. The first frame is the reference.",
  "describe photos": "MegaLoc turns each fused frame into an 8,448-number descriptor. Two views look alike when the cosine of their descriptors is high.",
  "render and describe": "The store is rendered from every position of the lattice at each allowed height, pitch and heading, in chunks, and each render is described with MegaLoc. Views = positions × heights × pitches × headings.",
  "rank 1": "Each view scores the sum over the fused frames of the cosine between that frame's descriptor and the render at the view's heading plus the frame's offset. The best places, kept apart, go to level 2.",
  "rank 2": "Each view scores the cosine between the first photo's descriptor and the render. The best places, kept apart, go to verification.",
  verification: "Each place is refined (renders of nearby poses matched to the first photo with XFeat and LighterGlue, the best one solved to a pose), then a solved place tracks the first photos. Most photos tracked, then median inliers, wins.",
};
const LEVEL_TEXT = {
  1: "Coarse search: a wide lattice, scored by the fused frames. The best places become the centres of level 2.",
  2: "Fine search: a tight lattice within a radius of each level 1 place, scored by the first photo alone. The best places go to verification.",
};
const MS_PER_S = 1000;
const MIN_PER_UNIT_SECONDS = 0.05;

function unitName(stage) {
  if (stage === "verification") return "places";
  if (stage === "yaw offsets") return "frame pairs";
  if (stage === "describe photos") return "photos";
  return "views";
}

function perUnit(seconds, units) {
  if (units === 0 || seconds < MIN_PER_UNIT_SECONDS) return "";
  const each = seconds / units;
  return each >= 1 ? ` · ${each.toFixed(1)} s each` : ` · ${(each * MS_PER_S).toFixed(1)} ms each`;
}

function stageSeconds(stage, nowS) {
  return (stage.endS ?? nowS) - stage.startS;
}

function barRow(label, seconds, totalS) {
  const row = element("div", "bar-row");
  const bar = element("div", "bar");
  bar.style.width = `${Math.max(0.5, (100 * seconds) / Math.max(totalS, 1e-9))}%`;
  row.append(element("span", "bar-label", label), bar);
  return row;
}

function stageCard(stage, title, text, totalS, nowS) {
  const seconds = stageSeconds(stage, nowS);
  const card = element("div", `step ${stage.endS === null ? "running" : "done"}`);
  card.append(element("div", "step-title", title), element("div", "step-text muted", text));
  card.append(element("div", "step-metrics", `${stage.units.toLocaleString()} ${unitName(stage.stage)}${perUnit(seconds, stage.units)} · ${seconds.toFixed(1)} s · ${((100 * seconds) / Math.max(totalS, 1e-9)).toFixed(0)} % of the run`));
  if (stage.renderS != null && stage.describeS != null) {
    card.append(barRow(`render ${stage.renderS.toFixed(1)} s`, stage.renderS, seconds), barRow(`describe ${stage.describeS.toFixed(1)} s`, stage.describeS, seconds));
  } else {
    card.append(barRow("", seconds, totalS));
  }
  return card;
}

function verificationCard(pass, stage, totalS, nowS) {
  const card = stageCard(stage, "verification", STEP_TEXT.verification, totalS, nowS);
  const table = element("table", "verify-table");
  const head = element("tr");
  head.append(...["place", "refine views", "refine s", "track s", "tracked", "inliers", "verdict"].map((h) => element("th", "", h)));
  table.append(head);
  for (const [rank, result] of [...pass.verification.entries()].sort((a, b) => a[0] - b[0])) {
    const row = element("tr", `verdict ${result.status}`);
    const cells = result.status === "running" || result.status === "queued"
      ? [`#${rank}`, "", "", "", "", "", result.status]
      : [`#${rank}`, result.refineViews ?? "–", result.refineS?.toFixed(1) ?? "–", result.trackS?.toFixed(1) ?? "–", `${result.framesTracked}/${result.framesTotal}`, result.inliers, result.status];
    row.append(...cells.map((c) => element("td", "", String(c))));
    table.append(row);
  }
  card.append(table);
  return card;
}

// The whole process in order, each step with what it does and what this run spent on it.
export function renderProcess(container, state) {
  const nowS = state.ended ? state.ended.timeS : state.timeS;
  const totalS = Math.max(nowS, 1e-9);
  const nodes = [element("h2", "", `The run in order · ${formatClock(nowS)} in total`)];
  for (const stage of state.prelude) nodes.push(stageCard(stage, stage.stage, STEP_TEXT[stage.stage], totalS, nowS));
  for (const pass of state.passes) {
    if (pass.stages.length === 0 && !pass.relaxation) continue;
    const block = element("section", "process-pass");
    block.append(element("h3", "", `Search pass ${pass.index}`), element("p", "muted", priorsLine(pass.priors)));
    for (const stage of pass.stages) {
      const level = /^level (\d)/.exec(stage.stage)?.[1];
      if (stage.stage === "verification") {
        block.append(verificationCard(pass, stage, totalS, nowS));
        continue;
      }
      const kind = stage.stage.replace(/^level \d: /, "");
      const text = kind === "rank" ? STEP_TEXT[`rank ${level}`] : level ? `${LEVEL_TEXT[level]} ${STEP_TEXT[kind]}` : STEP_TEXT[kind];
      block.append(stageCard(stage, stage.stage, text, totalS, nowS));
    }
    if (pass.relaxation) {
      const r = pass.relaxation;
      block.append(element("div", "relaxed", `Nothing verified, so ${r.prior} is widened (${r.half_width_before} → ${r.half_width_after}) and the search runs again.`));
    }
    nodes.push(block);
  }
  if (state.fix) nodes.push(element("div", "verdict accepted", `Result: ${state.fix.east_m.toFixed(0)}, ${state.fix.north_m.toFixed(0)} m, heading ${state.fix.heading_deg.toFixed(0)}°, ${state.fix.inliers} inliers.`));
  container.replaceChildren(...nodes);
}
