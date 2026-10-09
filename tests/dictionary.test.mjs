import {test} from 'node:test';
import assert from 'node:assert/strict';
import {fresh,validateProject} from '../src/model.ts';
test('1,000-ID projects accept high IDs but retain uniqueness and bounds',()=>{
 const p=fresh();p.dictionary='DICT_4X4_1000';
 const m={uid:'high',id:999,x:2,y:2,z:0,yaw:0,size:.2,mount:'floor'};
 p.markers=[m];assert.equal(validateProject(p).markers[0].id,999);
 assert.throws(()=>validateProject({...p,markers:[{...m,id:1000}]}));
 assert.throws(()=>validateProject({...p,markers:[m,{...m,uid:'duplicate'}]}));
 assert.throws(()=>validateProject({...p,dictionary:'DICT_4X4_50'}));
});
