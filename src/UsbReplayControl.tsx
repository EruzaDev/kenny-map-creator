import { useEffect, useRef, useState } from 'react';
import { UsbReplay } from './usb-replay';
import type { MotionReplay } from './usb-replay';

async function request(action: string, body?: Record<string, number>) {
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), action === 'status' ? 800 : 220);
  try {
    const response = await fetch('/api/usb/' + action, {
      method: body === undefined ? 'GET' : 'POST', signal: abort.signal,
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
    });
    const result = await response.json();
    if (!response.ok || result.ok === false) throw Error(result.detail || result.error || 'USB command rejected');
    return result;
  } finally { clearTimeout(timer); }
}

export function UsbReplayControl({ replay, onFrame, onDriving }: {
  replay: MotionReplay | null; onFrame: (index: number) => void; onDriving: (active: boolean) => void;
}) {
  const [running, setRunning] = useState(false);
  const [power, setPower] = useState(70);
  const [message, setMessage] = useState('Ready for a map replay. No sensors required.');
  const runner = useRef<UsbReplay | null>(null);
  if (!runner.current) runner.current = new UsbReplay(request);
  const active = useRef(false);
  const callbacks = useRef({ onFrame, onDriving });
  callbacks.current = { onFrame, onDriving };
  async function stop() {
    try { await runner.current!.stop(); setMessage('ESP32 stopped and disarmed.'); }
    catch (error) { setMessage(String(error)); }
  }
  useEffect(() => {
    if (active.current) void stop();
  }, [replay]);
  useEffect(() => {
    const leave = () => {
      if (!active.current) return;
      void stop();
      navigator.sendBeacon('/api/usb/stop', new Blob(['{}'], { type: 'application/json' }));
    };
    const hidden = () => { if (document.hidden) leave(); };
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') void stop(); };
    window.addEventListener('blur', leave); window.addEventListener('pagehide', leave);
    document.addEventListener('visibilitychange', hidden); document.addEventListener('keydown', escape);
    return () => {
      leave(); window.removeEventListener('blur', leave); window.removeEventListener('pagehide', leave);
      document.removeEventListener('visibilitychange', hidden); document.removeEventListener('keydown', escape);
    };
  }, []);
  async function drive() {
    if (!replay || active.current) return;
    active.current = true; setRunning(true); callbacks.current.onDriving(true);
    setMessage('Driving ESP32 from the map replay · real-time 1×.');
    try {
      await runner.current!.run(replay, power, index => callbacks.current.onFrame(index));
      setMessage('Map command playback finished. ESP32 stopped.');
    } catch (error) { setMessage(String(error)); }
    finally { active.current = false; setRunning(false); callbacks.current.onDriving(false); }
  }
  return <div className="navigation-panel"><div className="section-heading">ESP32 USB · OPEN-LOOP MAP DRIVE</div>
    <p className="hint">Run your map test, then drive the robot using that replay’s movement commands. Map position is simulated; physical sensors are not used.</p>
    <label className="field">Motor power · {power}%<input aria-label="USB motor power" type="range" min="0" max="100" step="5" value={power} disabled={running} onChange={e => setPower(Number(e.target.value))} /></label>
    <button className="full primary" disabled={!replay || running || !replay.frames.every(f => !!f.command)} onClick={() => void drive()}>▶ Drive ESP32 with this map</button>
    <button className="full" onClick={() => void stop()}>■ STOP ROBOT</button>
    <p role="status" className="hint">{message}</p>
    <p className="hint">USB uses real-time 1× playback and the ESP32 watchdog. Commands are scaled to firmware limits and this power setting; distance is not calibrated.</p>
  </div>;
}
