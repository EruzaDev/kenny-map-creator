import { useMemo } from 'react';
import { toLocal } from './model';
import type { Project } from './model';

export type CloudMap = { environment: Project; sha256: string; revision: number; updated: number };

export function CloudMapPreview({ map }: { map: CloudMap }) {
  const project = map.environment, grid = project.grid;
  const width = grid.width * grid.resolution, height = grid.height * grid.resolution;
  const image = useMemo(() => {
    const canvas = document.createElement('canvas');
    canvas.width = grid.width; canvas.height = grid.height;
    const context = canvas.getContext('2d')!;
    const pixels = context.createImageData(grid.width, grid.height);
    for (let y = 0; y < grid.height; y++) for (let x = 0; x < grid.width; x++) {
      const cell = grid.data[(grid.height - y - 1) * grid.width + x], index = (y * grid.width + x) * 4;
      pixels.data.set(cell === 100 ? [50, 67, 73, 255] : cell === -1 ? [176, 186, 190, 255] : [248, 250, 248, 255], index);
    }
    context.putImageData(pixels, 0, 0);
    return canvas.toDataURL();
  }, [grid]);
  function visual(point: number[]) { const p = toLocal(point, grid); return [p[0], height - p[1]]; }
  const scale = Math.max(width, height) / 40;
  return <figure className="cloud-map-preview">
    <svg role="img" aria-label="Map fetched from Render" viewBox={`0 0 ${width} ${height}`}>
      <image href={image} width={width} height={height} style={{ imageRendering: 'pixelated' }} />
      {project.obstacles.map((o, i) => <polygon key={o.uid || i} points={[[o.x, o.y], [o.x + o.width, o.y], [o.x + o.width, o.y + o.depth], [o.x, o.y + o.depth]].map(visual).map(p => p.join(',')).join(' ')} fill={o.kind === 'prohibited' ? '#e5982c' : '#50665f'} />)}
      {project.markers.map(m => {
        const [x, y] = visual([m.x, m.y]);
        return <g key={m.id}><circle cx={x} cy={y} r={scale * .45} fill="#0b996f" /><text x={x + scale * .5} y={y - scale * .4} fontSize={scale} fill="#075c43">{m.id}</text></g>;
      })}
      {(() => { const [x, y] = visual(project.start); return <circle cx={x} cy={y} r={scale * .65} fill="#3478d5" />; })()}
    </svg>
    <figcaption><strong>{project.name || 'Render map'}</strong><br />{width.toFixed(2)} × {height.toFixed(2)} m · {project.markers.length} ArUcos<br />Revision {map.revision} · {new Date(map.updated * 1000).toLocaleString()}<br /><span title={map.sha256}>SHA-256: {map.sha256.slice(0, 12)}…</span></figcaption>
  </figure>;
}
