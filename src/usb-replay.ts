export type MotionFrame = { command?: { v: number; w: number }; event: string };
export type MotionReplay = { frames: MotionFrame[]; dt: number };
type Request = (action: string, body?: Record<string, number>) => Promise<any>;

export function usbMotion(command: { v: number; w: number }, power: number) {
  if (![command.v, command.w, power].every(Number.isFinite) || power < 0 || power > 100) throw Error('Invalid USB motion');
  // Scale both axes together to retain curvature within firmware limits.
  const factor = Math.min(1, .1 / Math.max(Math.abs(command.v), .1), .6 / Math.max(Math.abs(command.w), .6)) * power / 100;
  return { v: command.v * factor, w: command.w * factor };
}

export class UsbReplay {
  private generation = 0;
  private active = false;
  private request: Request;
  private now: () => number;
  private sleep: (ms: number) => Promise<void>;
  constructor(request: Request, now = () => performance.now(),
              sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))) {
    this.request = request; this.now = now; this.sleep = sleep;
  }

  async stop() {
    ++this.generation;
    this.active = false;
    await this.request('stop', {});
  }

  async run(replay: MotionReplay, power: number, onFrame: (index: number) => void) {
    if (this.active) throw Error('USB replay is already running');
    if (!Number.isFinite(replay.dt) || replay.dt < .02 || replay.dt > 1 || replay.frames.length < 2 || replay.frames.length > 3001) throw Error('Invalid replay timing');
    for (const frame of replay.frames) {
      if (!frame.command) throw Error('Run a new navigation test to record USB commands');
      usbMotion(frame.command, power);
    }
    this.active = true;
    const mine = ++this.generation;
    let armAttempted = false;
    try {
      const status = await this.request('status');
      if (mine !== this.generation) return;
      if (!status.ready || status.estop || status.armed) throw Error('ESP32 not ready or another controller is armed');
      armAttempted = true;
      const { lease } = await this.request('arm', {});
      if (mine !== this.generation) { await this.request('stop', {}); return; }
      if (!Number.isInteger(lease) || lease <= 0) throw Error('Invalid ESP32 lease');
      let seq = 0;
      const start = this.now();
      let lastTick = start;
      while (mine === this.generation) {
        const now = this.now();
        if (now - lastTick > 180) throw Error('Replay clock delayed; USB drive stopped');
        lastTick = now;
        const index = Math.floor((now - start) / (replay.dt * 1000)) + 1;
        if (index >= replay.frames.length) { onFrame(replay.frames.length - 1); break; }
        const frame = replay.frames[index];
        if (['collision', 'cliff'].includes(frame.event)) throw Error('Replay hazard reached; USB drive stopped');
        const command = usbMotion(frame.command!, power);
        await this.request('drive', { lease, seq: ++seq, ...command });
        if (mine !== this.generation) break;
        onFrame(index - 1);
        await this.sleep(Math.max(0, 50 - (this.now() - now)));
      }
    } finally {
      if (mine === this.generation) {
        this.active = false;
        ++this.generation;
        if (armAttempted) await this.request('stop', {});
      }
    }
  }
}
