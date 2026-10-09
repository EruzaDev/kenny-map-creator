import {test} from 'node:test'
import assert from 'node:assert/strict'
import {NearGoalAnnouncement} from '../src/near-audio.ts'

function mockAudio() {
 const oldContext=globalThis.AudioContext, oldFetch=globalThis.fetch
 let plays=0,stops=0
 class Context {
  destination={}
  async resume(){}
  async decodeAudioData(){return {}}
  createBufferSource(){return {connect(){},start(){plays++},stop(){stops++}}}
  async close(){}
 }
 globalThis.AudioContext=Context
 globalThis.fetch=async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)})
 return {plays:()=>plays,stops:()=>stops,restore:()=>{globalThis.AudioContext=oldContext;globalThis.fetch=oldFetch}}
}

test('announce at exactly five meters, once across repeated frames and re-entry',async()=>{
 const mock=mockAudio();const player=new NearGoalAnnouncement('/im-near.mp3')
 try {
  await player.enable()
  assert.equal(await player.playIfNear(5.01),false)
  assert.equal(await player.playIfNear(5),true)
  assert.equal(await player.playIfNear(.7),false)
  assert.equal(await player.playIfNear(6),false)
  assert.equal(await player.playIfNear(.8),false)
  assert.equal(mock.plays(),1)
  player.reset()
  assert.equal(await player.playIfNear(.2),true)
  assert.equal(mock.plays(),2)
 } finally {player.dispose();mock.restore()}
})

test('a new run cancels a pending old announcement',async()=>{
 const mock=mockAudio();let finish
 globalThis.fetch=()=>new Promise(resolve=>{finish=()=>resolve({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)})})
 const player=new NearGoalAnnouncement('/im-near.mp3')
 try {
  const pending=player.playIfNear(.5)
  player.reset();finish()
  assert.equal(await pending,false);assert.equal(mock.plays(),0)
  assert.equal(await player.playIfNear(.5),true)
  assert.equal(mock.plays(),1)
 } finally {player.dispose();mock.restore()}
})

test('invalid or far distances never announce and muting does not re-arm the run',async()=>{
 const mock=mockAudio(),player=new NearGoalAnnouncement('/im-near.mp3')
 try {
  for(const distance of [NaN,Infinity,-1,5.001]) assert.equal(await player.playIfNear(distance),false)
  assert.equal(mock.plays(),0)
  await player.playIfNear(.5);player.silence()
  assert.equal(await player.playIfNear(.5),false)
  assert.equal(mock.plays(),1)
 } finally {player.dispose();mock.restore()}
})

test('audio errors do not cause repeated frame retries; an explicit enable can retry',async()=>{
 const mock=mockAudio(),player=new NearGoalAnnouncement('/im-near.mp3')
 try {
  globalThis.fetch=async()=>({ok:false})
  await assert.rejects(()=>player.playIfNear(.5),/could not be loaded/)
  assert.equal(await player.playIfNear(.5),false)
  globalThis.fetch=async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(0)})
  await player.enable()
  assert.equal(await player.playIfNear(.5),true)
  assert.equal(mock.plays(),1)
 } finally {player.dispose();mock.restore()}
})
