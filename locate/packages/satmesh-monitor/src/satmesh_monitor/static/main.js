import { createMap } from "./map.js";
import { formatClock, renderConvergence, renderFusion, renderLadder, renderLegend, renderPriors, renderProgress } from "./panels.js";
import { similarityRange, stateAt } from "./reducer.js";

const POLL_INTERVAL_MS = 1000;
const SPEEDS = [1, 10, 60];
const SCRUBBER_STEPS_PER_SECOND = 100;
const MAX_FRAME_ADVANCE_S = 1;

const $ = (id) => document.getElementById(id);

const events = [];
let finished = false;
let durationS = 0;
let timeS = 0;
let following = true;
let playing = false;
let speed = SPEEDS[0];
let mapView = null;
let lastFrameMs = null;
let mapEventCount = -1;
let mapRangeHigh;
let spreadCache = { count: -1, series: [] };

async function fetchMore() {
  const response = await fetch(`/api/events?after=${events.length}`);
  const page = await response.json();
  events.push(...page.events);
  finished = page.finished;
  durationS = events.length ? events[events.length - 1].time_s : 0;
  return page;
}

function setUpStatic(start, hasPhotos) {
  $("area").textContent = `${(start.bounds.east_max_m - start.bounds.east_min_m).toFixed(0)} × ${(start.bounds.north_max_m - start.bounds.north_min_m).toFixed(0)} m, levels ${start.levels.map((l) => `${l.level}: ${l.spacing_m} m spacing, ${l.positions} positions`).join("; ")}`;
  if (hasPhotos && start.photos.length > 0) {
    const photo = $("photo");
    photo.src = `/api/photo/${encodeURIComponent(start.photos[0])}`;
    photo.alt = start.photos[0];
    $("photo-panel").hidden = false;
  }
  mapView = createMap($("map"), start);
}

function draw() {
  const state = stateAt(events, timeS);
  const range = similarityRange(events);
  const visibleCount = events.filter((event) => event.time_s <= timeS).length;
  if (visibleCount !== mapEventCount || range?.high !== mapRangeHigh) {
    mapEventCount = visibleCount;
    mapRangeHigh = range?.high;
    mapView.update(state, range);
  }
  renderPriors($("priors"), state.priors);
  renderProgress($("stages"), state);
  renderLegend($("legend"), range);
  renderFusion($("fusion"), state, (name) => `/api/photo/${encodeURIComponent(name)}`);
  renderLadder($("ladder"), state);
  if (spreadCache.count !== events.length) {
    spreadCache = { count: events.length, series: stateAt(events, Infinity).spread };
  }
  renderConvergence($("convergence"), spreadCache.series, state, durationS);
  $("clock").textContent = `${formatClock(timeS)} / ${formatClock(durationS)}`;
  $("status").textContent = state.ended
    ? state.ended.ok ? "finished, fix found" : "finished, no fix"
    : finished ? "replay" : following ? "live" : "behind live";
  const scrubber = $("scrubber");
  scrubber.max = String(Math.round(durationS * SCRUBBER_STEPS_PER_SECOND));
  scrubber.value = String(Math.round(timeS * SCRUBBER_STEPS_PER_SECOND));
}

function setTime(newTimeS) {
  timeS = Math.min(Math.max(0, newTimeS), durationS);
  following = timeS >= durationS && !finished;
  draw();
}

function frame(nowMs) {
  if (playing && lastFrameMs !== null) {
    const advance = Math.min(((nowMs - lastFrameMs) / 1000) * speed, MAX_FRAME_ADVANCE_S * speed);
    setTime(timeS + advance);
    if (timeS >= durationS) setPlaying(false);
  }
  lastFrameMs = nowMs;
  requestAnimationFrame(frame);
}

function setPlaying(value) {
  playing = value;
  $("play").textContent = playing ? "Pause" : "Play";
}

async function poll() {
  if (finished) return;
  await fetchMore();
  if (following) timeS = durationS;
  draw();
  setTimeout(poll, POLL_INTERVAL_MS);
}

function wireControls() {
  $("play").addEventListener("click", () => {
    if (!playing && timeS >= durationS) timeS = 0;
    setPlaying(!playing);
  });
  $("scrubber").addEventListener("input", (e) => {
    setPlaying(false);
    setTime(Number(e.target.value) / SCRUBBER_STEPS_PER_SECOND);
  });
  $("live").addEventListener("click", () => {
    setPlaying(false);
    setTime(durationS);
  });
  for (const button of document.querySelectorAll("[data-speed]")) {
    button.addEventListener("click", () => {
      speed = Number(button.dataset.speed);
      for (const other of document.querySelectorAll("[data-speed]")) other.classList.toggle("active", other === button);
    });
  }
}

async function main() {
  wireControls();
  let page = await fetchMore();
  while (events.length === 0 || events[0].kind !== "run_start") {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    page = await fetchMore();
  }
  setUpStatic(events[0], page.has_photos);
  timeS = durationS;
  following = !finished;
  draw();
  requestAnimationFrame(frame);
  setTimeout(poll, POLL_INTERVAL_MS);
}

main();
