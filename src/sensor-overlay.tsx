import {scanRays} from './sensor-geometry';
import type {SensorFrame, SensorScan} from './sensor-geometry';

export function SensorOverlay({sensors, visual, lidar, depth, floor}: {
  sensors: SensorFrame; visual: (point: number[]) => number[];
  lidar: boolean; depth: boolean; floor: boolean;
}) {
  function rays(scan: SensorScan, color: string) {
    return scanRays(scan).map((ray, i) => {
      const start=visual(ray.start), end=visual(ray.end);
      return <g key={i}><line x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]}
        stroke={ray.valid ? color : '#ef4444'} strokeWidth=".015"
        opacity={ray.valid ? .45 : .3} strokeDasharray={ray.valid ? undefined : '.08 .06'} />
        {ray.hit && <circle cx={end[0]} cy={end[1]} r=".045" fill={color} />}</g>;
    });
  }
  const camera=sensors.depth;
  const half=sensors.camera_hfov_deg*Math.PI/360;
  const cone=[visual(camera.origin),...Array.from({length:17},(_,i)=>{
    const heading=camera.origin[2]-half+2*half*i/16;
    return visual([camera.origin[0]+camera.max_range*Math.cos(heading),camera.origin[1]+camera.max_range*Math.sin(heading)]);
  })];
  return <g pointerEvents="none" aria-label="Recorded simulated sensor observations">
    {depth && <polygon points={cone.map(p=>p.join(',')).join(' ')} fill="#8b5cf6" opacity=".06" />}
    {lidar && <g>{rays(sensors.lidar,'#0284c7')}</g>}
    {depth && <g>{rays(camera,'#9333ea')}</g>}
    {floor && <g>{rays(sensors.floor,'#ca8a04')}</g>}
  </g>;
}
