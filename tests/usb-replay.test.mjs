import { test } from 'node:test';
import assert from 'node:assert/strict';
import { UsbReplay, usbMotion } from '../src/usb-replay.ts';

const replay = { dt: .1, frames: Array.from({ length: 4 }, () => ({ event: 'running', command: { v: .3, w: .3 } })) };
function fixture() {
  let clock = 0;
  const calls = [];
  const request = async (action, body) => {
    calls.push([action, body]);
    if (action === 'status') return { ready: true, estop: false, armed: false };
    if (action === 'arm') return { lease: 123 };
    return { ok: true };
  };
  const runner = new UsbReplay(request, () => clock, async ms => { clock += ms; });
  return { runner, calls, request };
}

test('real-time replay sends guarded motion in order, repeats at 20 Hz, stops at end', async () => {
  const { runner, calls } = fixture();
  const indices = [];
  await runner.run(replay, 20, index => indices.push(index));
  const drive = calls.filter(([action]) => action === 'drive');
  assert.equal(drive.length, 6);
  assert.deepEqual(drive.map(([, body]) => body.seq), [1, 2, 3, 4, 5, 6]);
  assert.equal(drive[0][1].lease, 123);
  assert.ok(Math.abs(drive[0][1].v - .02) < 1e-8);
  assert.deepEqual(indices, [0, 0, 1, 1, 2, 2, 3]);
  assert.equal(calls.at(-1)[0], 'stop');
});

test('power and limits preserve curvature; invalid commands rejected before ARM', async () => {
  const result = usbMotion({ v: .6, w: .3 }, 100);
  assert.ok(Math.abs(result.v - .1) < 1e-8);
  assert.ok(Math.abs(result.w - .05) < 1e-8);
  const { runner, calls } = fixture();
  await assert.rejects(runner.run({ dt: .1, frames: [{ event: 'running' }, { event: 'running' }] }, 20, () => {}));
  assert.equal(calls.length, 0);
  assert.throws(() => usbMotion({ v: NaN, w: 0 }, 20));
});

test('late ARM response after STOP cannot resume motion', async () => {
  let resolveArm;
  const calls = [];
  const runner = new UsbReplay(async action => {
    calls.push(action);
    if (action === 'status') return { ready: true, armed: false };
    if (action === 'arm') return new Promise(resolve => { resolveArm = resolve; });
    return { ok: true };
  });
  const running = runner.run(replay, 20, () => {});
  await new Promise(resolve => setImmediate(resolve));
  await runner.stop();
  resolveArm({ lease: 123 });
  await running;
  assert.deepEqual(calls, ['status', 'arm', 'stop', 'stop']);
});

test('lost ARM acknowledgment and delayed clock both stop/disarm', async () => {
  const actions = [];
  const runner = new UsbReplay(async action => {
    actions.push(action);
    if (action === 'status') return { ready: true, armed: false };
    if (action === 'arm') throw Error('ACK lost');
    return { ok: true };
  });
  await assert.rejects(runner.run(replay, 20, () => {}), /ACK lost/);
  assert.equal(actions.at(-1), 'stop');
  const { calls, request } = fixture();
  let clock = 0;
  const late = new UsbReplay(request, () => clock, async () => { clock += 250; });
  await assert.rejects(late.run(replay, 20, () => {}), /clock delayed/);
  assert.equal(calls.filter(([action]) => action === 'drive').length, 1);
  assert.equal(calls.at(-1)[0], 'stop');
});

test('occupied Wi-Fi session is refused without stopping its owner', async () => {
  const actions = [];
  const runner = new UsbReplay(async action => { actions.push(action); return { ready: true, armed: true }; });
  await assert.rejects(runner.run(replay, 20, () => {}), /another controller/);
  assert.deepEqual(actions, ['status']);
});
