import test from 'node:test';
import assert from 'node:assert/strict';
import {relativeMarkerEstimates} from '../src/marker-distance.ts';

const markers=[{id:34,x:1,y:1,z:0},{id:35,x:3,y:1,z:0},{id:36,x:1,y:2,z:1}];
const packet={dictionary:'DICT_4X4_50',age_s:.1,detections:[
  {id:34,camera_position_m:[0,0,1],depth_samples:20},
  {id:35,camera_position_m:[0,0,2.5],depth_samples:10},
  {id:36,camera_position_m:[0,0,2],depth_samples:9}]};

test('same-frame depth spacing previews an offset without changing surveyed markers',()=>{
  const proposals=relativeMarkerEstimates(markers,packet);
  assert.equal(proposals.length,2);
  assert.equal(proposals[0].anchor_id,34);
  assert.deepEqual([proposals[0].x,proposals[0].y,proposals[0].measured_distance_m],[2.5,1,1.5]);
  assert.equal(markers[1].x,3);
  assert.equal(proposals[1].measured_distance_m,0);
  assert.deepEqual(relativeMarkerEstimates(markers,{...packet,age_s:2}),[]);
});

test('selected marker can anchor a provisional pair',()=>{
  const estimate=relativeMarkerEstimates(markers,packet,35).find(m=>m.id===34);
  assert.equal(estimate.x,1.5);
  assert.equal(estimate.mapped_distance_m,2);
});
