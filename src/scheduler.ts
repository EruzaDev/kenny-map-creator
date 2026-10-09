import type { Project } from './model';

export type CallRequest = { id: string; caller: string; markerId: number; createdAt: number };
export type RankedCall = CallRequest & { distance: number; overdue: boolean };
export const MAX_WAIT_MS = 5 * 60 * 1000;

// Advisory dispatch order only; the guarded simulator remains responsible for
// route feasibility. Distance is to the arrival point, not a wall marker face.
export function rankCalls(project: Project, calls: CallRequest[], position: [number, number], now: number): RankedCall[] {
  if (![...position, now].every(Number.isFinite)) throw Error('Invalid scheduler position/time');
  return calls.filter(call => project.markers.some(m => m.id === call.markerId)).map(call => {
    const marker = project.markers.find(m => m.id === call.markerId)!;
    const offset = marker.mount === 'wall' ? .5 : 0;
    const target = [marker.x + Math.cos(marker.yaw) * offset, marker.y + Math.sin(marker.yaw) * offset];
    return { ...call, distance: Math.hypot(target[0] - position[0], target[1] - position[1]),
      overdue: now - call.createdAt >= MAX_WAIT_MS };
  }).sort((a, b) => Number(b.overdue) - Number(a.overdue) ||
    (a.overdue ? a.createdAt - b.createdAt : a.distance - b.distance) ||
    a.createdAt - b.createdAt || a.id.localeCompare(b.id));
}
