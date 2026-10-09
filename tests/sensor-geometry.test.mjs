import {test} from 'node:test';
import assert from 'node:assert/strict';
import {scanRays} from '../src/sensor-geometry.ts';
test('rotate recorded rays from acquisition pose and retain valid hits',()=>{
 const scan={origin:[2,3,Math.PI/2],angles:[0,-Math.PI/2],ranges:[1,2],valid:[true,true],hits:[true,false],max_range:6,age_steps:1};
 const rays=scanRays(scan);
 assert.ok(Math.abs(rays[0].end[0]-2)<1e-9);assert.equal(rays[0].end[1],4);
 assert.deepEqual(rays[1].end,[4,3]);assert.ok(rays[0].hit);assert.ok(!rays[1].hit);
});
test('invalid rays show unknown range, never a hit',()=>{
 const rays=scanRays({origin:[0,0,0],angles:[0],ranges:[.1],valid:[false],hits:[true],max_range:6,age_steps:0});
 assert.deepEqual(rays[0].end,[6,0]);assert.equal(rays[0].hit,false);
});
