import type { Project } from './model';
import { toLocal, toWorld } from './model.ts';

export type Pose2 = [number,number,number];
const wrap=(value:number)=>Math.atan2(Math.sin(value),Math.cos(value));

export function transformPoint(point:number[], transform:Pose2): [number,number] {
  const c=Math.cos(transform[2]),s=Math.sin(transform[2]);
  return [transform[0]+c*point[0]-s*point[1],transform[1]+s*point[0]+c*point[1]];
}
export function transformPose(pose:number[], transform:Pose2): Pose2 {
  return [...transformPoint(pose,transform),wrap(pose[2]+transform[2])];
}
export function alignmentFromPlacement(placement:Pose2, measured:number[]): Pose2 {
  const angle=wrap(placement[2]-measured[2]),c=Math.cos(angle),s=Math.sin(angle);
  return [placement[0]-c*measured[0]+s*measured[1],placement[1]-s*measured[0]-c*measured[1],angle];
}

export function suggestPlacement(project:Project, basePoints:number[][], seed:Pose2) {
  const grid=project.grid,maxError=.3;
  const obstacles=project.obstacles.filter(o=>o.kind!=='prohibited'&&o.bottom<=.38&&o.bottom+o.height>=.38);
  const prohibited=project.obstacles.filter(o=>o.kind==='prohibited');
  if (!grid.data.some(v=>v===100)&&!obstacles.length) throw Error('Draw/import physical walls before matching scans. No-go areas are not physical walls.');
  if (basePoints.length<20) throw Error('At least 20 measured scan returns are required.');
  const stride=Math.max(1,Math.ceil(basePoints.length/80));
  const points=basePoints.filter((_,i)=>i%stride===0);
  const cache=new Map<string,number>();
  const radius=Math.ceil(maxError/grid.resolution);
  const distance=(point:number[])=>{
    const local=toLocal(point,grid),x=Math.floor(local[0]/grid.resolution),y=Math.floor(local[1]/grid.resolution);
    if(x<0||y<0||x>=grid.width||y>=grid.height)return maxError;
    const key=x+','+y;
    let minimum=cache.get(key);
    if(minimum==null){
      minimum=maxError;
      for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++){
        const px=x+dx,py=y+dy;
        if(px>=0&&py>=0&&px<grid.width&&py<grid.height&&grid.data[py*grid.width+px]===100){
          const world=toWorld([(px+.5)*grid.resolution,(py+.5)*grid.resolution],grid);
          if(!prohibited.some(o=>world[0]>=o.x&&world[0]<=o.x+o.width&&world[1]>=o.y&&world[1]<=o.y+o.depth))
            minimum=Math.min(minimum,Math.hypot(dx,dy)*grid.resolution);
        }
      }
      cache.set(key,minimum);
    }
    for(const obstacle of obstacles){
      const dx=Math.max(obstacle.x-point[0],0,point[0]-obstacle.x-obstacle.width);
      const dy=Math.max(obstacle.y-point[1],0,point[1]-obstacle.y-obstacle.depth);
      minimum=Math.min(minimum,Math.hypot(dx,dy));
    }
    return minimum;
  };
  const score=(pose:Pose2)=>{
    const errors=points.map(point=>distance(transformPoint(point,pose)));
    return {mean:errors.reduce((a,b)=>a+b,0)/errors.length,matched:errors.filter(v=>v<=.1).length/errors.length};
  };
  let bestPose=seed,best=score(seed);
  const before={...best};
  for(let heading=-20;heading<=20;heading+=5)for(let dx=-.5;dx<=.5001;dx+=.1)for(let dy=-.5;dy<=.5001;dy+=.1){
    const candidate:Pose2=[seed[0]+dx,seed[1]+dy,wrap(seed[2]+heading*Math.PI/180)];
    const candidateScore=score(candidate);
    if(candidateScore.mean<best.mean-.0001){best=candidateScore;bestPose=candidate;}
  }
  return {pose:bestPose,before,after:best,samples:points.length};
}
