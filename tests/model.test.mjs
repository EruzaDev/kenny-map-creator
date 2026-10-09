import {test} from 'node:test'
import assert from 'node:assert/strict'
import {fresh,toLocal,toWorld,validateProject,newUid} from '../src/model.ts'

test('ROS map coordinates round-trip with translation and rotation',()=>{
 const g={...fresh().grid,origin:[-4.25,2.3,Math.PI/3]}
 for(const point of [[0,0],[8.6,3.2],[-1,5]]) {
  const restored=toWorld(toLocal(point,g),g)
  assert.ok(Math.abs(restored[0]-point[0])<1e-12)
  assert.ok(Math.abs(restored[1]-point[1])<1e-12)
 }
})
test('fresh map uses measured dimensions and free-space occupancy',()=>{
 const p=fresh(12,8)
 assert.equal(p.grid.width,240);assert.equal(p.grid.height,160)
 assert.equal(p.grid.data.length,38400)
 assert.equal(validateProject(p),p)
})
test('reject malformed occupancy and repeated marker IDs on project import',()=>{
 const bad=fresh();bad.grid.data[3]=42
 assert.throws(()=>validateProject(bad),/Invalid map grid/)
 const p=fresh();const m={uid:'1',id:7,x:1,y:1,z:0,yaw:0,size:.2,mount:'floor'}
 p.markers=[m,{...m,uid:'2'}]
 assert.throws(()=>validateProject(p),/duplicate marker/)
})

test('reject excessive map dimensions before allocating occupancy data',()=>{
 assert.throws(()=>fresh(100000,100000),/1000 meters/)
 assert.throws(()=>fresh(.001,1),/0.05 and 1000 meters/)
})

test('large blank maps reduce grid detail instead of stopping at 100 meters',()=>{
 const p=fresh(150,150)
 assert.equal(p.grid.width,2000);assert.equal(p.grid.height,2000)
 assert.equal(p.grid.resolution,.075)
 assert.equal(p.grid.data.length,4_000_000)
})

test('object IDs work on plain HTTP robot origins without randomUUID',()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'crypto')
 const random=globalThis.crypto.getRandomValues.bind(globalThis.crypto)
 Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues:random}})
 try {
  const first=newUid(), second=newUid()
  assert.match(first,/^[0-9a-f]{32}$/)
  assert.notEqual(first,second)
 } finally { Object.defineProperty(globalThis,'crypto',original) }
})

test('selected ArUco marker overrides stale coordinates and follows marker movement',()=>{
 const p=fresh();p.markers=[{uid:'marker',id:0,x:2,y:3,z:0,yaw:0,size:.2,mount:'floor'}]
 p.destination_marker_id=0;p.goal=[9,9]
 assert.deepEqual(validateProject(p).goal,[2,3])
 p.markers[0].x=4
 assert.deepEqual(validateProject(p).goal,[4,3])
 const reopened=JSON.parse(JSON.stringify(p))
 assert.deepEqual(validateProject(reopened).goal,[4,3])
 p.markers=[]
 assert.throws(()=>validateProject(p),/missing/)
})

test('wall-marker destination uses its facing direction and a half-meter default offset',()=>{
 const p=fresh();p.markers=[{uid:'wall-marker',id:5,x:3,y:2,z:1,yaw:Math.PI/2,size:.2,mount:'wall'}]
 p.destination_marker_id=5
 assert.deepEqual(validateProject(p).goal,[3,2.5])
 p.destination_offset_m=.75
 assert.deepEqual(validateProject(p).goal,[3,2.75])
 p.destination_offset_m=-1
 assert.throws(()=>validateProject(p),/offset/)
})
