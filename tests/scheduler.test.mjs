import {test} from 'node:test';
import assert from 'node:assert/strict';
import {rankCalls, MAX_WAIT_MS} from '../src/scheduler.ts';
const project = {markers: [
 {id: 1, x: 1, y: 0, yaw: 0, mount: 'floor'},
 {id: 2, x: 9, y: 0, yaw: 0, mount: 'floor'},
 {id: 3, x: 0, y: 0, yaw: Math.PI, mount: 'wall'},
]};
const calls = [
 {id:'a', caller:'Far', markerId:2, createdAt:0},
 {id:'b', caller:'Near', markerId:1, createdAt:1},
];
test('rank nearest caller and recompute from new position without mutating queue', () => {
 assert.deepEqual(rankCalls(project,calls,[0,0],10).map(c=>c.id),['b','a']);
 assert.deepEqual(rankCalls(project,calls,[9,0],10).map(c=>c.id),['a','b']);
 assert.equal(calls[0].id,'a');
});
test('oldest overdue caller takes precedence to prevent starvation', () => {
 assert.equal(rankCalls(project,calls,[0,0],MAX_WAIT_MS+10)[0].id,'a');
});
test('deleted destinations excluded; wall approach offset used', () => {
 const queue=[{id:'c',caller:'Wall',markerId:3,createdAt:0},{id:'x',caller:'Missing',markerId:99,createdAt:0}];
 const ranked=rankCalls(project,queue,[0,0],10);
 assert.equal(ranked.length,1);
 assert.equal(ranked[0].distance,.5);
});
test('equal distance breaks ties by request age', () => {
 assert.deepEqual(rankCalls(project,calls,[5,0],10).map(c=>c.id),['a','b']);
 assert.throws(()=>rankCalls(project,calls,[NaN,0],10));
});
