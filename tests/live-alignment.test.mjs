import test from 'node:test';
import assert from 'node:assert/strict';
import { alignmentFromPlacement, transformPoint, transformPose, suggestPlacement } from '../src/live-alignment.ts';
import { fresh } from '../src/model.ts';

const close=(actual,expected)=>actual.forEach((v,i)=>assert.ok(Math.abs(v-expected[i])<1e-8,`${actual} != ${expected}`));
test('placement anchors measured pose and rotates scan points without changing measurements',()=>{
  const measured=[10,20,Math.PI/2],placed=[2,3,0];
  const alignment=alignmentFromPlacement(placed,measured);
  close(transformPose(measured,alignment),placed);
  close(transformPoint([10,21],alignment),[3,3]);
  close(transformPose([10,22,Math.PI/2],alignment),[4,3,0]);
  assert.deepEqual(measured,[10,20,Math.PI/2]);
});
test('nearby alignment search improves actual scan-wall agreement and preserves project',()=>{
  const project=fresh(8,8);
  project.obstacles=[
    {uid:'right',kind:'wall',x:5,y:0,width:.1,depth:8,bottom:0,height:2},
    {uid:'top',kind:'wall',x:0,y:6,width:8,depth:.1,bottom:0,height:2}
  ];
  const points=[];
  for(let i=0;i<20;i++){points.push([2,-1+i*.15]);points.push([-1+i*.15,3]);}
  const serialized=JSON.stringify(project);
  const result=suggestPlacement(project,points,[2.7,2.7,0]);
  assert.ok(result.after.mean<result.before.mean);
  assert.ok(result.after.matched>.9);
  assert.ok(Math.abs(result.pose[0]-3)<.11&&Math.abs(result.pose[1]-3)<.11);
  assert.equal(JSON.stringify(project),serialized);
});
test('no-go areas and unavailable scans do not create fictional wall matches',()=>{
  const project=fresh(4,4);
  project.obstacles=[{uid:'restricted',kind:'prohibited',x:0,y:0,width:4,depth:4,bottom:0,height:2}];
  assert.throws(()=>suggestPlacement(project,Array.from({length:20},()=>[1,1]),[1,1,0]),/physical walls/);
  project.obstacles=[];project.grid.data.fill(100);
  assert.throws(()=>suggestPlacement(project,[],[1,1,0]),/20 measured/);
});
