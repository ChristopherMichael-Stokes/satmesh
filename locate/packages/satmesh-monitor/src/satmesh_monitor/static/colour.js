// Viridis (matplotlib), nine evenly spaced stops, interpolated linearly in sRGB.
const VIRIDIS = [
  "#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725",
];

function channels(hex) {
  return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
}

export function viridis(fraction) {
  const clamped = Math.min(1, Math.max(0, fraction));
  const position = clamped * (VIRIDIS.length - 1);
  const lower = Math.min(Math.floor(position), VIRIDIS.length - 2);
  const mix = position - lower;
  const [from, to] = [channels(VIRIDIS[lower]), channels(VIRIDIS[lower + 1])];
  const [red, green, blue] = from.map((value, i) => Math.round(value + (to[i] - value) * mix));
  return `rgb(${red},${green},${blue})`;
}

export const VIRIDIS_CSS_GRADIENT = `linear-gradient(to right, ${VIRIDIS.join(", ")})`;
