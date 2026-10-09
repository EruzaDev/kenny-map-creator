export type SensorScan = {
  origin: number[]; angles: number[]; ranges: number[];
  valid: boolean[]; hits: boolean[]; max_range: number; age_steps: number;
};
export type SensorFrame = {lidar: SensorScan; depth: SensorScan; floor: SensorScan; camera_hfov_deg: number};
export function scanRays(scan: SensorScan) {
  return scan.angles.map((angle, i) => {
    const valid = scan.valid[i] === true;
    const range = valid ? scan.ranges[i] : scan.max_range;
    const heading = scan.origin[2] + angle;
    return {start: scan.origin.slice(0,2),
      end: [scan.origin[0] + range * Math.cos(heading), scan.origin[1] + range * Math.sin(heading)],
      valid, hit: valid && scan.hits[i] === true};
  });
}
