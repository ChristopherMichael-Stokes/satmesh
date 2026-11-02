// The monitor's state is a pure function of the events up to a time.

export function cellKey(level, cell) {
  return `${level}:${cell.east_m}:${cell.north_m}`;
}

// Root-mean-square distance of the places from their centroid, metres.
export function spatialSpread(places) {
  if (places.length === 0) return 0;
  const east = places.reduce((sum, p) => sum + p.east_m, 0) / places.length;
  const north = places.reduce((sum, p) => sum + p.north_m, 0) / places.length;
  const meanSquare =
    places.reduce((sum, p) => sum + (p.east_m - east) ** 2 + (p.north_m - north) ** 2, 0) / places.length;
  return Math.sqrt(meanSquare);
}

function relaxed(priors, event) {
  if (event.prior === "area") {
    return priors.position && { ...priors, position: { ...priors.position, radius_m: event.half_width_after } };
  }
  const key = event.prior === "heading" ? "heading_deg" : "pitch_deg";
  return priors[key] && { ...priors, [key]: { ...priors[key], half_width: event.half_width_after } };
}

function newPass(index, priors, startS) {
  return { index, priors, startS, endS: null, candidates: new Map(), verification: new Map(), relaxation: null };
}

function applyEvent(state, event) {
  const pass = state.passes[state.passes.length - 1];
  switch (event.kind) {
    case "run_start":
      state.start = event;
      state.priors = event.priors;
      state.passes.push(newPass(1, event.priors, event.time_s));
      break;
    case "fusion_window":
      state.fusion = event;
      break;
    case "stage_start":
      state.stages.push({ stage: event.stage, units: event.units, startS: event.time_s, endS: null });
      break;
    case "stage_end": {
      const open = state.stages.findLast((s) => s.stage === event.stage && s.endS === null);
      if (open) open.endS = event.time_s;
      break;
    }
    case "cell_batch":
      for (const cell of event.cells) state.cells.set(cellKey(event.level, cell), { level: event.level, ...cell });
      break;
    case "candidates":
      state.candidates.set(event.level, event.places);
      pass.candidates.set(event.level, event.places);
      state.spread.push({ timeS: event.time_s, spreadM: spatialSpread(event.places), count: event.places.length });
      break;
    case "verification_start":
      state.verification.set(event.rank, { status: "running" });
      pass.verification.set(event.rank, { status: "running" });
      break;
    case "verification_result": {
      const result = {
        status: event.accepted ? "accepted" : "rejected",
        inliers: event.inliers,
        framesTracked: event.frames_tracked,
        framesTotal: event.frames_total,
      };
      state.verification.set(event.rank, result);
      pass.verification.set(event.rank, result);
      break;
    }
    case "prior_relaxed":
      state.priors = relaxed(state.priors, event) ?? state.priors;
      pass.endS = event.time_s;
      pass.relaxation = event;
      state.verification = new Map();
      state.passes.push(newPass(pass.index + 1, state.priors, event.time_s));
      break;
    case "fix":
      state.fix = event;
      break;
    case "run_end":
      state.ended = { ok: event.ok, timeS: event.time_s };
      pass.endS = event.time_s;
      break;
  }
}

export function stateAt(events, timeS) {
  const state = {
    timeS,
    start: null,
    priors: null,
    stages: [],
    cells: new Map(),
    candidates: new Map(),
    verification: new Map(),
    passes: [],
    fusion: null,
    spread: [],
    fix: null,
    ended: null,
  };
  for (const event of events) {
    if (event.time_s > timeS) break;
    applyEvent(state, event);
  }
  return state;
}

// Candidate lists are drawn per level; verification results belong to the highest level's ranks.
export function verifiedLevel(state) {
  return Math.max(0, ...state.candidates.keys());
}

export function verificationOf(state, level, rank) {
  if (level !== verifiedLevel(state) || state.verification.size === 0) return null;
  return state.verification.get(rank) ?? { status: "queued" };
}

export function similarityRange(events) {
  let low = Infinity;
  let high = -Infinity;
  for (const event of events) {
    if (event.kind !== "cell_batch") continue;
    for (const cell of event.cells) {
      if (cell.similarity === null) continue;
      low = Math.min(low, cell.similarity);
      high = Math.max(high, cell.similarity);
    }
  }
  return low <= high ? { low, high } : null;
}
