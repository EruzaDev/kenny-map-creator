export type Grid = {
  width: number;
  height: number;
  resolution: number;
  origin: [number, number, number];
  data: number[];
};
export type Marker = {
  uid: string;
  id: number;
  x: number;
  y: number;
  z: number;
  yaw: number;
  size: number;
  mount: 'floor' | 'wall';
};
export type Obstacle = {
  uid: string;
  kind: 'wall' | 'obstacle' | 'prohibited';
  x: number;
  y: number;
  width: number;
  depth: number;
  bottom: number;
  height: number;
};
export type Project = {
  version: 1;
  name: string;
  frame_id: 'map';
  units: 'meters';
  dictionary: 'DICT_4X4_50' | 'DICT_4X4_1000';
  grid: Grid;
  markers: Marker[];
  obstacles: Obstacle[];
  start: [number, number];
  goal: [number, number];
  destination_marker_id?: number | null;
  destination_offset_m?: number;
  background?: {
    data: string;
    width: number;
    height: number;
  };
};
export const MAX_BLANK_MAP_DIMENSION = 1000;
const MIN_BLANK_MAP_DIMENSION = .05;
const MAX_GRID_CELLS = 4_000_000;
export function fresh(w = 12, h = 8): Project {
  if (!Number.isFinite(w) || !Number.isFinite(h) || w < MIN_BLANK_MAP_DIMENSION || h < MIN_BLANK_MAP_DIMENSION || w > MAX_BLANK_MAP_DIMENSION || h > MAX_BLANK_MAP_DIMENSION) {
    throw Error(`Map dimensions must be between ${MIN_BLANK_MAP_DIMENSION} and ${MAX_BLANK_MAP_DIMENSION} meters.`);
  }
  // Keep the 5 cm detail used for normal rooms, but avoid allocating an
  // impractically large grid for larger environments.
  const resolution = Math.max(.05, Math.sqrt(w * h / MAX_GRID_CELLS), w / 4000, h / 4000),
    width = Math.ceil(w / resolution),
    height = Math.ceil(h / resolution);
  if (width < 1 || height < 1 || width > 4000 || height > 4000 || width * height > MAX_GRID_CELLS) throw Error('Map dimensions exceed the supported grid size (4 million cells).');
  return {
    version: 1,
    name: 'CCS Ground Floor',
    frame_id: 'map',
    units: 'meters',
    dictionary: 'DICT_4X4_50',
    grid: {
      width,
      height,
      resolution,
      origin: [0, 0, 0],
      data: Array(width * height).fill(0)
    },
    markers: [],
    obstacles: [],
    start: [1, 1],
    goal: [Math.max(1, w - 1), Math.max(1, h - 1)]
  };
}
export function toLocal(p: number[], g: Grid): [number, number] {
  const [ox, oy, a] = g.origin,
    x = p[0] - ox,
    y = p[1] - oy;
  return [Math.cos(a) * x + Math.sin(a) * y, -Math.sin(a) * x + Math.cos(a) * y];
}
export function toWorld(p: number[], g: Grid): [number, number] {
  const [ox, oy, a] = g.origin;
  return [ox + Math.cos(a) * p[0] - Math.sin(a) * p[1], oy + Math.sin(a) * p[0] + Math.cos(a) * p[1]];
}
export function validateProject(p: Project) {
  if (p.version !== 1 || p.frame_id !== 'map' || p.units !== 'meters' || !['DICT_4X4_50', 'DICT_4X4_1000'].includes(p.dictionary)) throw Error('Unsupported project format');
  const g = p.grid;
  if (!g || !Number.isInteger(g.width) || !Number.isInteger(g.height) || g.width < 1 || g.height < 1 || g.width > 4000 || g.height > 4000 || g.width * g.height > 4e6 || !Number.isFinite(g.resolution) || g.resolution < .005 || g.resolution > 1 || g.origin.length !== 3 || !g.origin.every(Number.isFinite) || g.data.length !== g.width * g.height || !g.data.every(v => [-1, 0, 100].includes(v))) throw Error('Invalid map grid');
  if (!Array.isArray(p.markers) || !Array.isArray(p.obstacles) || p.start.length !== 2 || p.goal.length !== 2 || ![...p.start, ...p.goal].every(Number.isFinite)) throw Error('Invalid project objects');
  const ids = new Set<number>();
  for (const m of p.markers) {
    if (!Number.isInteger(m.id) || m.id < 0 || m.id >= (p.dictionary === 'DICT_4X4_1000' ? 1000 : 50) || ids.has(m.id) || ![m.x, m.y, m.z, m.yaw, m.size].every(Number.isFinite) || m.size < .01 || m.size > 1 || m.z < 0 || !['floor', 'wall'].includes(m.mount)) throw Error('Invalid or duplicate marker');
    ids.add(m.id);
  }
  for (const o of p.obstacles) {
    if (!['wall', 'obstacle', 'prohibited'].includes(o.kind) || ![o.x, o.y, o.width, o.depth, o.bottom, o.height].every(Number.isFinite) || Math.min(o.width, o.depth, o.height) <= 0 || o.bottom < 0) throw Error('Invalid obstacle');
  }
  return withDestination(p);
}
export async function requestFile(path: string, payload: unknown) {
  const r = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({
      detail: r.statusText
    }));
    throw Error(e.detail || 'Request failed');
  }
  return r;
}
export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function newUid(): string {
  // randomUUID is restricted to secure contexts; the robot may serve HTTP on a LAN.
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** A marker is the destination landmark; wall arrivals stop in front of its face. */
export function resolvedGoal(project: Project): [number, number] {
  if (project.destination_marker_id == null) return project.goal;
  if (!Number.isInteger(project.destination_marker_id)) throw Error('Destination marker ID must be an integer.');
  const marker = project.markers.find(m => m.id === project.destination_marker_id);
  if (!marker) throw Error('The destination ArUco marker is missing. Choose another marker.');
  const offset = project.destination_offset_m ?? (marker.mount === 'wall' ? .5 : 0);
  if (!Number.isFinite(offset) || offset < 0 || offset > 2) throw Error('Destination approach offset must be 0–2 meters.');
  return [marker.x + Math.cos(marker.yaw) * offset, marker.y + Math.sin(marker.yaw) * offset];
}
export function withDestination(project: Project): Project {
  return project.destination_marker_id == null ? project : {
    ...project,
    goal: resolvedGoal(project)
  };
}
