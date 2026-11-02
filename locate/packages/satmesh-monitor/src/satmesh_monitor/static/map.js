import { viridis } from "./colour.js";
import { circlePolygon, makeProjection, rectanglePolygon, squarePolygon, wedgePolygon } from "./geo.js";
import { verificationOf } from "./reducer.js";

const maplibregl = globalThis.maplibregl;

const ATTRIBUTION = "Esri, Maxar, Earthstar Geographics, and the GIS User Community";
const IMAGERY_MIN_ZOOM = 10;
const IMAGERY_MAX_ZOOM = 20;
const MAP_MAX_ZOOM = 22;
const FIT_PADDING_PX = 40;
const RENDERED_CELL_COLOUR = "#9aa0a6";
const EMPTY_COLLECTION = { type: "FeatureCollection", features: [] };

function feature(geometry, properties = {}) {
  return { type: "Feature", geometry, properties };
}

function collection(features) {
  return { type: "FeatureCollection", features };
}

function cellColour(cell, range) {
  if (cell.state === "rendered" || cell.similarity === null || range === null) return RENDERED_CELL_COLOUR;
  const span = range.high - range.low;
  return viridis(span > 0 ? (cell.similarity - range.low) / span : 1);
}

function spacingOf(start, level) {
  return start.levels.find((l) => l.level === level).spacing_m;
}

function overlayFeatures(state, range, project) {
  const { start, priors } = state;
  const bounds = [feature(rectanglePolygon(project, start.bounds))];
  const cells = [...state.cells.values()].map((cell) =>
    feature(squarePolygon(project, cell.east_m, cell.north_m, spacingOf(start, cell.level)), {
      colour: cellColour(cell, range),
      level: cell.level,
    }),
  );
  const position = priors.position;
  const circle = position ? [feature(circlePolygon(project, position.east_m, position.north_m, position.radius_m))] : [];
  const wedge =
    position && priors.heading_deg
      ? [
          feature(
            wedgePolygon(
              project, position.east_m, position.north_m, position.radius_m,
              priors.heading_deg.centre, priors.heading_deg.half_width,
            ),
          ),
        ]
      : [];
  return { bounds, cells, circle, wedge };
}

function candidateElement(level, place, verification) {
  const element = document.createElement("div");
  element.className = `candidate level-${level} ${verification?.status ?? "unverified"}`;
  const disc = document.createElement("div");
  disc.className = "disc";
  disc.textContent = String(place.rank);
  element.append(disc);
  if (verification) {
    const label = document.createElement("div");
    label.className = "label";
    label.textContent =
      verification.inliers === undefined
        ? verification.status
        : `${verification.status} ${verification.inliers} in, ${verification.framesTracked}/${verification.framesTotal} fr`;
    element.append(label);
  }
  return element;
}

function fixElement() {
  const element = document.createElement("div");
  element.className = "fix";
  element.innerHTML =
    '<svg viewBox="-12 -16 24 32" width="30" height="40"><path d="M0,-14 L9,12 L0,6 L-9,12 Z"/></svg>';
  return element;
}

export function createMap(container, start) {
  const project = makeProjection(start.origin_latitude_deg, start.origin_longitude_deg);
  const map = new maplibregl.Map({
    container,
    maxZoom: MAP_MAX_ZOOM,
    attributionControl: false,
    style: {
      version: 8,
      sources: {
        imagery: {
          type: "raster",
          tiles: ["/tiles/{z}/{x}/{y}.jpg"],
          tileSize: 256,
          minzoom: IMAGERY_MIN_ZOOM,
          maxzoom: IMAGERY_MAX_ZOOM,
          attribution: ATTRIBUTION,
        },
      },
      layers: [
        { id: "background", type: "background", paint: { "background-color": "#1b1d21" } },
        { id: "imagery", type: "raster", source: "imagery" },
      ],
    },
  });
  map.addControl(new maplibregl.AttributionControl({ compact: false }), "bottom-right");
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");

  const { bounds } = start;
  map.fitBounds([project(bounds.east_min_m, bounds.north_min_m), project(bounds.east_max_m, bounds.north_max_m)], {
    padding: FIT_PADDING_PX,
    animate: false,
  });

  const markers = new Map();
  let ready = false;
  let pending = null;

  function addOverlay(id, type, paint) {
    map.addSource(id, { type: "geojson", data: EMPTY_COLLECTION });
    map.addLayer({ id, type, source: id, paint });
  }

  map.on("load", () => {
    addOverlay("bounds", "line", { "line-color": "#ffffff", "line-width": 2, "line-dasharray": [4, 3] });
    addOverlay("cells", "fill", { "fill-color": ["get", "colour"], "fill-opacity": 0.55, "fill-outline-color": "rgba(255,255,255,0.35)" });
    addOverlay("circle", "fill", { "fill-color": "#ffb000", "fill-opacity": 0.12 });
    addOverlay("circle-line", "line", { "line-color": "#ffb000", "line-width": 2 });
    addOverlay("wedge", "line", { "line-color": "#ff6b3d", "line-width": 2 });
    ready = true;
    if (pending) update(...pending);
  });

  function syncMarkers(wanted) {
    for (const [key, marker] of markers) {
      if (!wanted.has(key)) {
        marker.remove();
        markers.delete(key);
      }
    }
    for (const [key, { element, lngLat, rotation }] of wanted) {
      markers.get(key)?.remove();
      const marker = new maplibregl.Marker({
        element,
        rotation,
        rotationAlignment: "map",
        pitchAlignment: "map",
      })
        .setLngLat(lngLat)
        .addTo(map);
      markers.set(key, marker);
    }
  }

  function update(state, range) {
    if (!ready) {
      pending = [state, range];
      return;
    }
    const overlays = overlayFeatures(state, range, project);
    map.getSource("bounds").setData(collection(overlays.bounds));
    map.getSource("cells").setData(collection(overlays.cells));
    map.getSource("circle").setData(collection(overlays.circle));
    map.getSource("circle-line").setData(collection(overlays.circle));
    map.getSource("wedge").setData(collection(overlays.wedge));

    const wanted = new Map();
    for (const [level, places] of state.candidates) {
      for (const place of places) {
        wanted.set(`candidate:${level}:${place.rank}`, {
          element: candidateElement(level, place, verificationOf(state, level, place.rank)),
          lngLat: project(place.east_m, place.north_m),
          rotation: 0,
        });
      }
    }
    if (state.fix) {
      wanted.set("fix", {
        element: fixElement(),
        lngLat: project(state.fix.east_m, state.fix.north_m),
        rotation: state.fix.heading_deg,
      });
    }
    syncMarkers(wanted);
  }

  return { update };
}
