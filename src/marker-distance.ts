export type DepthMarker = {id:number; camera_position_m:number[]; depth_samples:number};
export type MarkerDistances = {dictionary:string; age_s:number; detections:DepthMarker[]};
export type MappedMarker = {id:number; x:number; y:number; z:number};
export type RelativeEstimate = {id:number; anchor_id:number; x:number; y:number; measured_distance_m:number; mapped_distance_m:number};

export function relativeMarkerEstimates(markers:MappedMarker[], packet:MarkerDistances|null|undefined,
  anchorId?:number):RelativeEstimate[] {
  if (!packet || !Number.isFinite(packet.age_s) || packet.age_s < 0 || packet.age_s > 1.5) return [];
  const saved = new Map(markers.map(marker => [marker.id,marker]));
  const seen = new Map<number,DepthMarker>();
  for (const detection of packet.detections || []) {
    const xyz = detection.camera_position_m;
    if (saved.has(detection.id) && detection.depth_samples > 0 && Array.isArray(xyz) &&
        xyz.length === 3 && xyz.every(v => typeof v === 'number' && Number.isFinite(v))) seen.set(detection.id,detection);
  }
  if (seen.size < 2) return [];
  const anchor = anchorId != null && seen.has(anchorId) ? anchorId : [...seen.keys()].sort((a,b)=>a-b)[0];
  const origin = saved.get(anchor)!;
  const originXYZ = seen.get(anchor)!.camera_position_m;
  return [...seen.entries()].filter(([id])=>id!==anchor).flatMap(([id,detection])=>{
    const mapped = saved.get(id)!;
    const dx=mapped.x-origin.x, dy=mapped.y-origin.y;
    const mappedDistance=Math.hypot(dx,dy);
    const delta=detection.camera_position_m.map((value,i)=>value-originXYZ[i]);
    const squared=delta.reduce((sum,value)=>sum+value*value,0);
    const height=mapped.z-origin.z;
    if (mappedDistance<.05 || squared < height*height || squared > 25) return [];
    const horizontal=Math.sqrt(squared-height*height);
    if (!Number.isFinite(horizontal)) return [];
    return [{id,anchor_id:anchor,x:origin.x+dx/mappedDistance*horizontal,
      y:origin.y+dy/mappedDistance*horizontal,measured_distance_m:horizontal,mapped_distance_m:mappedDistance}];
  });
}
