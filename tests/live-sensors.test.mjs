import test from 'node:test';
import assert from 'node:assert/strict';
import {finitePoints, liveAge, scanMatchesFrame} from '../src/live-sensors.ts';

test('live scan points filter invalid geometry and respect payload bounds',()=>{
  assert.deepEqual(finitePoints([[1,2],[NaN,3],['1',2],[1,2,3],null]),[[1,2]]);
  assert.equal(finitePoints(Array.from({length:1000},()=>[1,2])).length,720);
});
test('live acquisition age expires even while socket remains connected',()=>{
  assert.equal(liveAge(.1,1000,1500),.6);
  assert.equal(liveAge(null,1000,1500),Infinity);
  const scan={frame:'slam_map',age_s:.1};
  assert.equal(scanMatchesFrame(scan,'map',1000,1100),false);
  assert.equal(scanMatchesFrame(scan,'slam_map',1000,1100),true);
  assert.equal(scanMatchesFrame(scan,'slam_map',1000,1600),false);
});
