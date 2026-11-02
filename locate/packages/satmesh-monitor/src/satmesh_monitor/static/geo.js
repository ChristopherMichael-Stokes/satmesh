// Store ENU metres (east, north) to WGS84 longitude/latitude around the store origin.
// Metres per degree at latitude phi (WGS84 series, https://en.wikipedia.org/wiki/Geographic_coordinate_system#Length_of_a_degree):
//   lat: 111132.92 - 559.82 cos 2phi + 1.175 cos 4phi - 0.0023 cos 6phi
//   lon: 111412.84 cos phi - 93.5 cos 3phi + 0.118 cos 5phi

const CIRCLE_SEGMENTS = 72;
const WEDGE_SEGMENTS = 24;
const FULL_CIRCLE_DEG = 360;
const HALF_TURN_DEG = 180;

export function metresPerDegree(latitudeDeg) {
  const phi = (latitudeDeg * Math.PI) / 180;
  return {
    latitude: 111132.92 - 559.82 * Math.cos(2 * phi) + 1.175 * Math.cos(4 * phi) - 0.0023 * Math.cos(6 * phi),
    longitude: 111412.84 * Math.cos(phi) - 93.5 * Math.cos(3 * phi) + 0.118 * Math.cos(5 * phi),
  };
}

export function makeProjection(originLatitudeDeg, originLongitudeDeg) {
  const scale = metresPerDegree(originLatitudeDeg);
  return (eastM, northM) => [
    originLongitudeDeg + eastM / scale.longitude,
    originLatitudeDeg + northM / scale.latitude,
  ];
}

function closedRing(points) {
  return { type: "Polygon", coordinates: [[...points, points[0]]] };
}

export function squarePolygon(project, eastM, northM, sideM) {
  const half = sideM / 2;
  return closedRing([
    project(eastM - half, northM - half),
    project(eastM + half, northM - half),
    project(eastM + half, northM + half),
    project(eastM - half, northM + half),
  ]);
}

export function rectanglePolygon(project, bounds) {
  return closedRing([
    project(bounds.east_min_m, bounds.north_min_m),
    project(bounds.east_max_m, bounds.north_min_m),
    project(bounds.east_max_m, bounds.north_max_m),
    project(bounds.east_min_m, bounds.north_max_m),
  ]);
}

function bearingPoint(project, eastM, northM, radiusM, bearingDeg) {
  const bearing = (bearingDeg * Math.PI) / 180;
  return project(eastM + radiusM * Math.sin(bearing), northM + radiusM * Math.cos(bearing));
}

export function circlePolygon(project, eastM, northM, radiusM) {
  const ring = Array.from({ length: CIRCLE_SEGMENTS }, (_, i) =>
    bearingPoint(project, eastM, northM, radiusM, (FULL_CIRCLE_DEG * i) / CIRCLE_SEGMENTS),
  );
  return closedRing(ring);
}

// Heading is a compass bearing: degrees clockwise from north.
export function wedgePolygon(project, eastM, northM, radiusM, headingDeg, halfWidthDeg) {
  if (halfWidthDeg >= HALF_TURN_DEG) return circlePolygon(project, eastM, northM, radiusM);
  const arc = Array.from({ length: WEDGE_SEGMENTS + 1 }, (_, i) =>
    bearingPoint(
      project, eastM, northM, radiusM,
      headingDeg - halfWidthDeg + (2 * halfWidthDeg * i) / WEDGE_SEGMENTS,
    ),
  );
  return closedRing([project(eastM, northM), ...arc]);
}
