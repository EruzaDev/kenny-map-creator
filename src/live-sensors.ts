export type LiveScan = {
  frame: string | null;
  points: number[][];
  base_points: number[][];
  origin: number[] | null;
  age_s: number;
  samples: number;
  valid: number;
  range_max: number;
  reason?: string | null;
};

export function finitePoints(value: unknown, limit=720): number[][] {
  if (!Array.isArray(value)) return [];
  return value.slice(0,limit).filter((point): point is number[] =>
    Array.isArray(point) && point.length===2 && point.every(v=>typeof v==='number'&&Number.isFinite(v)));
}

export function liveAge(age: number | null | undefined, received: number, now: number): number {
  return age==null||!Number.isFinite(age)?Infinity:Math.max(0,age+(now-received)/1000);
}

export function scanMatchesFrame(scan: LiveScan | null | undefined, frame: string, received: number, now: number): boolean {
  return Boolean(scan && scan.frame===frame && liveAge(scan.age_s,received,now)<=.5);
}
