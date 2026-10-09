import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import JSZip from 'jszip';
import { fresh, toLocal, toWorld, validateProject, requestFile, download, newUid, withDestination, MAX_BLANK_MAP_DIMENSION } from './model';
import type { Project, Grid, Marker, Obstacle } from './model';
import './styles.css';
import nearSoundUrl from '../res/im near.mp3';
import { NearGoalAnnouncement } from './near-audio';
import { rankCalls } from './scheduler';
import type { CallRequest } from './scheduler';
import { modelLabel } from './model-label';
import { SensorOverlay } from './sensor-overlay';
import type { SensorFrame } from './sensor-geometry';
type Live = {
  type: 'map';
  revision: number;
  grid: Grid;
  pose?: number[];
  received_at: number;
  map_age_seconds?: number;
};
type Selection = {
  kind: 'marker' | 'obstacle' | 'start' | 'goal';
  uid: string;
};
type ModelChoice = {
  id: string;
  stage: string;
  bytes: number;
};
type ReplayFrame = {
  camera_visible_marker_ids?: number[];
  marker_localization_updated?: boolean;
  sensors?: SensorFrame;
  guard_reasons?: string[];
  step: number;
  pose: number[];
  estimate: number[];
  route: number[][];
  intervened: boolean;
  event: string;
  distance_to_destination_m: number;
  near_goal: boolean;
};
type Replay = {
  frames: ReplayFrame[];
  dt: number;
  model: string;
  seed: number;
  robot_radius: number;
  destination_marker_id: number | null;
  goal: [number, number];
  destination: [number, number];
  info: {
    event: string;
    steps: number;
    interventions: number;
    path_length: number;
    localization_error: number;
    no_route_steps: number;
    intervention_reasons: Record<string, number>;
  };
};
function App() {
  const [project, setProject] = useState<Project>(() => {
    try {
      return validateProject(JSON.parse(localStorage.getItem('kenny-project') || ''));
    } catch {
      return fresh();
    }
  });
  const [modelChoices, setModelChoices] = useState<ModelChoice[]>([]),
    [selectedModel, setSelectedModel] = useState(''),
    [modelError, setModelError] = useState('');
  const [testSteps, setTestSteps] = useState(1200),
    [testSeed, setTestSeed] = useState(42),
    [testing, setTesting] = useState(false);
  const [calls, setCalls] = useState<CallRequest[]>([]);
  const [callerName, setCallerName] = useState('');
  const [callerMarker, setCallerMarker] = useState('');
  const [activeCall, setActiveCall] = useState<CallRequest | null>(null);
  const [dispatchPosition, setDispatchPosition] = useState<[number, number] | null>(null);
  const dispatchBusy = useRef(false);
  const [replay, setReplay] = useState<Replay | null>(null),
    [frameIndex, setFrameIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [playSpeed, setPlaySpeed] = useState(2);
  const [nearSoundEnabled, setNearSoundEnabled] = useState(true);
  const [showLidar,setShowLidar]=useState(false);
  const [showDepth,setShowDepth]=useState(false);
  const [showFloor,setShowFloor]=useState(false);
  const [showMarkers,setShowMarkers]=useState(false);
  const nearAnnouncement = useRef<NearGoalAnnouncement | null>(null);
  if (!nearAnnouncement.current) nearAnnouncement.current = new NearGoalAnnouncement(nearSoundUrl);
  useEffect(() => () => nearAnnouncement.current?.dispose(), []);
  const projectRef = useRef(project);
  projectRef.current = project;
  useEffect(() => {
    void fetch('/api/models').then(async r => {
      if (!r.ok) throw Error('Model list unavailable');
      const choices: ModelChoice[] = await r.json();
      setModelChoices(choices);
      setSelectedModel(choices[0]?.id || '');
      if (!choices.length) setModelError('No checkpoints found. Place the trained run with config.json and contract.json in Kenny’s runs folder.');
    }).catch(() => setModelError('Start the backend server to load your trained models.'));
  }, []);
  useEffect(() => {
    setReplay(null);
    setPlaying(false);
    setFrameIndex(0);
    nearAnnouncement.current?.reset();
    setCalls([]);
    setActiveCall(null);
    setDispatchPosition(null);
  }, [project]);
  useEffect(() => {
    if (!playing || !replay) return;
    const timer = setInterval(() => setFrameIndex(i => Math.min(replay.frames.length - 1, i + 1)), replay.dt * 1000 / playSpeed);
    return () => clearInterval(timer);
  }, [playing, replay, playSpeed]);
  useEffect(() => {
    if (replay && frameIndex === replay.frames.length - 1) setPlaying(false);
  }, [frameIndex, replay]);
  const replayFrame = replay?.frames[frameIndex];
  useEffect(() => {
    if (!playing || !nearSoundEnabled || !replayFrame || ['collision', 'cliff'].includes(replayFrame.event)) return;
    void nearAnnouncement.current!.playIfNear(replayFrame.distance_to_destination_m).catch(() => setMessage('Audio could not play. Enable sound and press Play to try again.'));
  }, [playing, nearSoundEnabled, replayFrame]);
  async function runNavigation(call?: CallRequest) {
    if (dispatchBusy.current) return;
    if (!call && project.destination_marker_id == null) {
      setMessage('Choose a destination ArUco marker first.');
      return;
    }
    const marker = call ? project.markers.find(m => m.id === call.markerId) : null;
    const snapshot = withDestination(call ? { ...project,
      start: dispatchPosition ?? project.start,
      destination_marker_id: call.markerId,
      destination_offset_m: marker?.mount === 'wall' ? .5 : 0 } : project);
    const sourceProject = project;
    nearAnnouncement.current!.reset();
    if (nearSoundEnabled) void nearAnnouncement.current!.enable().catch(() => setMessage('The near-goal recording could not be enabled. Navigation can still be tested.'));
    setTesting(true);
    dispatchBusy.current = true;
    if (call) setActiveCall(call);
    setPlaying(false);
    setMessage('Running the selected trained model on your current map…');
    try {
      const result: Replay = await (await requestFile('/api/simulate', {
        environment: snapshot,
        model: selectedModel,
        steps: testSteps,
        seed: testSeed
      })).json();
      if (projectRef.current !== sourceProject) {
        setMessage('The map changed during the test. Run it again to preview the current map.');
        return;
      }
      setReplay(result);
      setFrameIndex(0);
      setPlaying(true);
      setMessage(`Test finished: ${result.info.event}. Replay shows the trained policy with Kenny’s safety guard enabled.`);
      if (call) {
        const pose = result.frames[result.frames.length - 1].pose;
        setDispatchPosition([pose[0], pose[1]]);
        if (result.info.event === 'success') {
          setCalls(waiting => waiting.filter(item => item.id !== call.id));
          setMessage(`Reached ${call.caller} (ID ${call.markerId}). Play the replay, then dispatch the next caller.`);
        } else {
          setMessage(`Request for ${call.caller} stopped: ${result.info.event}. Kept in queue; inspect before retrying.`);
        }
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Navigation test failed');
    } finally {
      setTesting(false);
      dispatchBusy.current = false;
      setActiveCall(null);
    }
  }
  const [history, setHistory] = useState<Project[]>([]),
    [future, setFuture] = useState<Project[]>([]);
  const [selected, setSelected] = useState<Selection | null>(null),
    [tool, setTool] = useState('select'),
    [snap, setSnap] = useState(true);
  const [zoom, setZoom] = useState(1),
    [pan, setPan] = useState<[number, number]>([0, 0]),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false);
  const [roomW, setRoomW] = useState(12),
    [roomH, setRoomH] = useState(8),
    [markerId, setMarkerId] = useState(0),
    [markerSize, setMarkerSize] = useState(.2),
    [markersPerPage, setMarkersPerPage] = useState<1 | 2 | 4>(1);
  const [calibrating, setCalibrating] = useState(false),
    [calPoints, setCalPoints] = useState<number[][]>([]),
    [realDistance, setRealDistance] = useState(1);
  const [bridge, setBridge] = useState(''),
    [live, setLive] = useState<Live | null>(null),
    [connection, setConnection] = useState('Disconnected'),
    [viewLive, setViewLive] = useState(false),
    [now, setNow] = useState(Date.now());
  const [opacity, setOpacity] = useState(.45);
  const svg = useRef<SVGSVGElement>(null),
    socket = useRef<WebSocket | null>(null),
    drag = useRef<{
      before: Project;
      selection: Selection;
      point: number[];
      original: number[];
    } | null>(null),
    panDrag = useRef<{
      point: number[];
      original: [number, number];
    } | null>(null);
  useEffect(() => {
    try {
      localStorage.setItem('kenny-project', JSON.stringify(project));
    } catch {
      setMessage('Browser storage is full. Download a project to preserve your work.');
    }
  }, [project]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      clearInterval(timer);
      socket.current?.close();
    };
  }, []);
  const grid = viewLive && live ? live.grid : project.grid,
    W = grid.width * grid.resolution,
    H = grid.height * grid.resolution;
  const stale = live ? now - live.received_at + (live.map_age_seconds || 0) * 1000 > 5000 : true;
  const image = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = grid.width;
    c.height = grid.height;
    const ctx = c.getContext('2d')!;
    const im = ctx.createImageData(c.width, c.height);
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const v = grid.data[(c.height - y - 1) * c.width + x],
        i = (y * c.width + x) * 4;
      const color = v === 100 ? [50, 67, 73] : v === -1 ? [176, 186, 190] : [248, 250, 248];
      im.data.set([...color, 255], i);
    }
    ctx.putImageData(im, 0, 0);
    return c.toDataURL();
  }, [grid]);
  const chosen = selected?.kind === 'marker' ? project.markers.find(m => m.uid === selected.uid) : selected?.kind === 'obstacle' ? project.obstacles.find(o => o.uid === selected.uid) : null;
  function commit(next: Project, before = project) {
    setHistory(h => [...h.slice(-29), before]);
    setFuture([]);
    setProject(withDestination(next));
  }
  function undo() {
    if (!history.length) return;
    setFuture(f => [project, ...f]);
    setProject(history[history.length - 1]);
    setHistory(h => h.slice(0, -1));
    setSelected(null);
  }
  function redo() {
    if (!future.length) return;
    setHistory(h => [...h, project]);
    setProject(future[0]);
    setFuture(f => f.slice(1));
    setSelected(null);
  }
  function local(e: {
    clientX: number;
    clientY: number;
  }) {
    const pt = svg.current!.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    const p = pt.matrixTransform(svg.current!.getScreenCTM()!.inverse());
    return [p.x, H - p.y];
  }
  function world(e: {
    clientX: number;
    clientY: number;
  }) {
    const p = toWorld(local(e), grid);
    return snap ? p.map(v => Math.round(v * 10) / 10) : p;
  }
  function visual(p: number[]) {
    const q = toLocal(p, grid);
    return [q[0], H - q[1]];
  }
  function chooseDestination(id: number) {
    const marker = project.markers.find(m => m.id === id);
    if (!marker) return;
    commit({
      ...project,
      destination_marker_id: id,
      destination_offset_m: marker.mount === 'wall' ? .5 : 0
    });
    setSelected({
      kind: 'goal',
      uid: 'goal'
    });
    setTool('select');
  }
  function add(kind: string, p: number[]) {
    if (viewLive) return;
    const [x, y] = p,
      uid = newUid();
    if (kind === 'goal') {
      const marker = project.markers.find(m => Math.hypot(m.x - x, m.y - y) <= Math.max(.35, m.size));
      if (marker) chooseDestination(marker.id);else setMessage('Click an ArUco marker or choose its ID under Destination marker.');
      return;
    }
    if (kind === 'marker') {
      if (project.markers.some(m => m.id === markerId)) {
        setMessage(`Marker ${markerId} is already placed. Choose a unique ID.`);
        return;
      }
      commit({
        ...project,
        markers: [...project.markers, {
          uid,
          id: markerId,
          x,
          y,
          z: 0,
          yaw: 0,
          size: markerSize,
          mount: 'floor'
        }]
      });
      setSelected({
        kind: 'marker',
        uid
      });
      const limit = project.dictionary === 'DICT_4X4_1000' ? 1000 : 50;
      const used = new Set([...project.markers.map(m => m.id), markerId]);
      const next = Array.from({length:limit}, (_,i) => (markerId + 1 + i) % limit).find(id => !used.has(id));
      setMarkerId(next ?? markerId);
    } else if (kind === 'start') {
      commit({
        ...project,
        [kind]: [x, y]
      });
      setSelected({
        kind,
        uid: kind
      });
    } else if (['wall', 'obstacle', 'prohibited'].includes(kind)) {
      const o: Obstacle = {
        uid,
        kind: kind as Obstacle['kind'],
        x,
        y,
        width: kind === 'wall' ? 2 : .7,
        depth: kind === 'wall' ? .15 : .7,
        bottom: 0,
        height: kind === 'wall' ? 2 : .5
      };
      commit({
        ...project,
        obstacles: [...project.obstacles, o]
      });
      setSelected({
        kind: 'obstacle',
        uid
      });
    }
  }
  function pointerDown(e: React.PointerEvent<SVGSVGElement>) {
    if (e.button !== 0 && e.button !== 1) return;
    const point = world(e);
    if (calibrating) {
      setCalPoints(p => [...p, local(e)].slice(-2));
      return;
    }
    if (tool === 'pan' || e.button === 1) {
      panDrag.current = {
        point: [e.clientX, e.clientY],
        original: pan
      };
      e.currentTarget.setPointerCapture(e.pointerId);
      return;
    }
    if (viewLive) return;
    if (tool === 'goal') {
      const target = (e.target as Element).closest('[data-kind="marker"]');
      const marker = project.markers.find(m => m.uid === target?.getAttribute('data-uid'));
      if (marker) chooseDestination(marker.id);else add(tool, point);
      return;
    }
    if (tool !== 'select') {
      add(tool, point);
      return;
    }
    const target = (e.target as Element).closest('[data-kind]');
    if (!target) {
      setSelected(null);
      return;
    }
    const selection = {
      kind: target.getAttribute('data-kind'),
      uid: target.getAttribute('data-uid')
    } as Selection;
    setSelected(selection);
    if (selection.kind === 'goal') return; // The goal follows its chosen landmark.
    const obj = selection.kind === 'marker' ? project.markers.find(m => m.uid === selection.uid) : selection.kind === 'obstacle' ? project.obstacles.find(o => o.uid === selection.uid) : null;
    const original = obj ? [obj.x, obj.y] : project[selection.kind as 'start' | 'goal'];
    drag.current = {
      before: project,
      selection,
      point,
      original
    };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function pointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (panDrag.current) {
      const scale = 1 / svg.current!.getScreenCTM()!.a;
      setPan([panDrag.current.original[0] - (e.clientX - panDrag.current.point[0]) * scale, panDrag.current.original[1] - (e.clientY - panDrag.current.point[1]) * scale]);
      return;
    }
    const d = drag.current;
    if (!d) return;
    const p = world(e),
      x = d.original[0] + p[0] - d.point[0],
      y = d.original[1] + p[1] - d.point[1];
    setProject(withDestination({
      ...d.before,
      ...(d.selection.kind === 'marker' ? {
        markers: d.before.markers.map(m => m.uid === d.selection.uid ? {
          ...m,
          x,
          y
        } : m)
      } : d.selection.kind === 'obstacle' ? {
        obstacles: d.before.obstacles.map(o => o.uid === d.selection.uid ? {
          ...o,
          x,
          y
        } : o)
      } : {
        [d.selection.kind]: [x, y]
      })
    }));
  }
  function pointerUp() {
    if (drag.current) {
      const before = drag.current.before;
      setHistory(h => [...h.slice(-29), before]);
      setFuture([]);
      drag.current = null;
    }
    panDrag.current = null;
  }
  function change(key: string, value: string | number) {
    if (!selected || !chosen) return;
    const group = selected.kind === 'marker' ? 'markers' : 'obstacles';
    if (key === 'id' && project.markers.some(m => m.id === value && m.uid !== selected.uid)) {
      setMessage('Marker ID is already used');
      return;
    }
    commit({
      ...project,
      ...(key === 'id' && selected.kind === 'marker' && (chosen as Marker).id === project.destination_marker_id ? {
        destination_marker_id: Number(value)
      } : {}),
      [group]: project[group].map(o => o.uid === selected.uid ? {
        ...o,
        [key]: value
      } : o)
    });
  }
  function remove() {
    if (!selected) return;
    if (selected.kind === 'marker') commit({
      ...project,
      markers: project.markers.filter(m => m.uid !== selected.uid),
      destination_marker_id: project.markers.find(m => m.uid === selected.uid)?.id === project.destination_marker_id ? null : project.destination_marker_id
    });
    if (selected.kind === 'obstacle') commit({
      ...project,
      obstacles: project.obstacles.filter(m => m.uid !== selected.uid)
    });
    setSelected(null);
  }
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try {
      await fn();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Operation failed');
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    const z = new JSZip();
    const {
      background,
      ...data
    } = project;
    z.file('project.json', JSON.stringify({
      ...data,
      background: background ? {
        ...background,
        data: undefined
      } : undefined
    }));
    if (background) z.file('background.txt', background.data);
    download(await z.generateAsync({
      type: 'blob'
    }), 'kenny-project.zip');
    setMessage('Project downloaded.');
  }
  async function open(file: File) {
    let p: Project;
    if (file.name.endsWith('.zip')) {
      const z = await JSZip.loadAsync(file);
      const entry = z.file('project.json') || z.file('environment.json');
      if (!entry) throw Error('Bundle contains no project.json or environment.json');
      p = JSON.parse(await entry.async('string'));
      if (p.background && z.file('background.txt')) p.background.data = await z.file('background.txt')!.async('string');
    } else p = JSON.parse(await file.text());
    validateProject(p);
    for (const m of p.markers) m.uid ||= newUid();
    for (const o of p.obstacles) o.uid ||= newUid();
    commit(p);
    setSelected(null);
    setViewLive(false);
    setPan([0, 0]);
    setZoom(1);
    setMessage('Project opened.');
  }
  async function floorplan(file: File) {
    if (project.obstacles.length || project.markers.length) throw Error('Start a blank project before calibrating a floor plan.');
    const data = await new Promise<string>((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as string);
      r.onerror = reject;
      r.readAsDataURL(file);
    });
    const im = new Image();
    im.src = data;
    await im.decode();
    const width = project.grid.width * project.grid.resolution,
      height = width * im.height / im.width;
    if (width * height / .05 ** 2 > 4e6) throw Error('Floor plan is too large');
    const next = fresh(width, height);
    next.name = project.name;
    next.background = {
      data,
      width,
      height
    };
    commit(next);
    setCalibrating(true);
    setCalPoints([]);
    setTool('select');
    setMessage('Select two points on the floor plan, then enter their real distance.');
  }
  function calibrate() {
    if (calPoints.length !== 2 || realDistance <= 0) return;
    const distance = Math.hypot(calPoints[1][0] - calPoints[0][0], calPoints[1][1] - calPoints[0][1]);
    if (distance < .001) {
      setMessage('Choose two different points.');
      return;
    }
    const factor = realDistance / distance;
    const width = Math.round(W * factor / .05),
      height = Math.round(H * factor / .05);
    if (width < 1 || height < 1 || width > 4000 || height > 4000 || width * height > 4e6) {
      setMessage("Calibrated dimensions exceed the supported grid size.");
      return;
    }
    const next = fresh(W * factor, H * factor);
    next.name = project.name;
    next.background = {
      ...project.background!,
      width: W * factor,
      height: H * factor
    };
    if (next.grid.width * next.grid.height > 4e6) {
      setMessage('Calibrated map exceeds 4 million cells.');
      return;
    }
    commit(next);
    setCalibrating(false);
    setCalPoints([]);
    setZoom(1);
    setPan([0, 0]);
    setMessage('Floor plan calibrated. Trace walls and obstacles over it.');
  }
  function connect() {
    setPlaying(false);
    nearAnnouncement.current!.silence();
    socket.current?.close();
    setConnection('Connecting…');
    setLive(null);
    setViewLive(true);
    const address = bridge.trim() || `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/live`;
    try {
      const url = new URL(address);
      if (!['ws:', 'wss:'].includes(url.protocol)) throw Error('Use a ws:// or wss:// bridge URL');
      const ws = new WebSocket(url);
      socket.current = ws;
      ws.onopen = () => {
        if (socket.current === ws) setConnection('Connected');
      };
      ws.onmessage = e => {
        if (socket.current !== ws) return;
        try {
          const packet = JSON.parse(e.data);
          if (packet.type === 'map') {
            const check = {
              ...fresh(),
              grid: packet.grid
            };
            validateProject(check);
            setLive({
              ...packet,
              received_at: Date.now()
            });
            setConnection('Connected');
          } else setConnection(packet.message || 'Unavailable');
        } catch {
          setConnection('Invalid mapping packet');
        }
      };
      ws.onerror = () => {
        if (socket.current === ws) setConnection('Connection failed');
      };
      ws.onclose = () => {
        if (socket.current !== ws) return;
        setConnection(c => c === 'Connected' ? 'Disconnected' : c);
        setViewLive(false);
      };
    } catch (e) {
      setConnection(String(e));
    }
  }
  function capture() {
    if (!live || stale || connection !== 'Connected') {
      setMessage('A fresh live map is required.');
      return;
    }
    const g = structuredClone(live.grid),
      start = toWorld([1, 1], g),
      goal = toWorld([g.width * g.resolution - 1, g.height * g.resolution - 1], g);
    commit({
      ...fresh(),
      name: project.name,
      grid: g,
      start,
      goal
    });
    setViewLive(false);
    setSelected(null);
    setPan([0, 0]);
    setZoom(1);
    setMessage('Map captured. Place start and goal in known free space, then add markers and obstacles.');
  }
  const tools = [['select', '↖', 'Select'], ['pan', '✥', 'Pan'], ['marker', '▦', 'ArUco marker'], ['wall', '━', 'Wall'], ['obstacle', '▧', 'Obstacle'], ['prohibited', '⊘', 'No-go area'], ['start', '◉', 'Robot start'], ['goal', '⚑', 'Choose destination']];
  const vW = (W + 1) / zoom,
    vH = (H + 1) / zoom;
  return <div className="studio"><header><div className="brand"><span className="brand-icon">K</span><div><strong>KENNY <em>ENVIRONMENT STUDIO</em></strong><small>Design the world Kenny moves through</small></div></div><div className="header-actions"><label className="button secondary">Open project<input type="file" accept=".zip,.json" onChange={e => {
            const f = e.target.files?.[0];
            if (f) void task(() => open(f));
            e.target.value = '';
          }} /></label><button onClick={() => void task(save)} disabled={busy}>Save project</button><button className="primary" disabled={busy || viewLive || project.destination_marker_id == null} onClick={() => void task(async () => {
          download(await (await requestFile('/api/export', project)).blob(), 'kenny-environment.zip');
          setMessage('Environment exported for Kenny.');
        })}>Export for Kenny ↗</button></div></header>
 <div className="workspace"><aside className="left"><div className="section-heading">ENVIRONMENT <span>01</span></div><input className="map-name" aria-label="Map name" value={project.name} onChange={e => setProject({
          ...project,
          name: e.target.value
        })} /><div className="dimensions"><Field label="Width · m" value={roomW} onChange={setRoomW} min={2} max={MAX_BLANK_MAP_DIMENSION} /><Field label="Length · m" value={roomH} onChange={setRoomH} min={2} max={MAX_BLANK_MAP_DIMENSION} /></div><p className="hint">Up to {MAX_BLANK_MAP_DIMENSION} m per side. Large maps use a larger cell size to stay responsive.</p><button className="full" onClick={() => {
          if (!confirm('Start a new blank map? Download your current project first to keep it.')) return;
          commit(fresh(roomW, roomH));
          setSelected(null);
          setViewLive(false);
          setZoom(1);
          setPan([0, 0]);
          setCalibrating(false);
        }}>＋ New blank map</button><label className="button full secondary">Upload floor plan<input type="file" accept="image/png,image/jpeg" onChange={e => {
            const f = e.target.files?.[0];
            if (f) void task(() => floorplan(f));
            e.target.value = '';
          }} /></label><label className="button full secondary">Import ROS map<input type="file" accept=".yaml,.yml,.pgm,.png" multiple onChange={e => {
            const files = Array.from(e.target.files || []);
            void task(async () => {
              const meta = files.find(f => /\.ya?ml$/i.test(f.name)),
                image = files.find(f => /\.(pgm|png)$/i.test(f.name));
              if (!meta || !image) throw Error('Select both map.yaml and its PGM/PNG image.');
              const bytes = new Uint8Array(await image.arrayBuffer());
              let binary = '';
              for (const b of bytes) binary += String.fromCharCode(b);
              const g = await (await requestFile('/api/import-map', {
                yaml: await meta.text(),
                image: btoa(binary)
              })).json();
              const p = {
                ...fresh(),
                grid: g,
                start: toWorld([1, 1], g),
                goal: toWorld([g.width * g.resolution - 1, g.height * g.resolution - 1], g)
              };
              validateProject(p);
              commit(p);
              setViewLive(false);
              setSelected(null);
            });
            e.target.value = '';
          }} /></label>
 <div className="section-heading separated">PLACE ON MAP <span>02</span></div><div className="tool-list">{tools.map(([id, icon, label]) => <button key={id} disabled={viewLive && !['select', 'pan'].includes(id)} className={tool === id ? 'active' : ''} onClick={() => setTool(id)} draggable={!viewLive} onDragStart={e => e.dataTransfer.setData('text/kenny-tool', id)}><b>{icon}</b><span>{label}</span>{tool === id && <i>●</i>}</button>)}</div><p className="hint">Drag an item onto the map, or choose a tool and click to place it.</p>
 <div className="marker-settings"><div className="section-heading">MARKER GENERATOR</div>
 <label className="field">Marker dictionary<select value={project.dictionary} onChange={e => {
   const dictionary = e.target.value as Project['dictionary'];
   if (dictionary === 'DICT_4X4_50' && project.markers.some(m => m.id >= 50)) {setMessage('Remove IDs above 49 before switching back to the 50-ID dictionary.');return;}
   commit({...project,dictionary}); setMarkerId(id => Math.min(id,dictionary === 'DICT_4X4_1000' ? 999 : 49));
 }}><option value="DICT_4X4_50">50 unique IDs · 0–49</option><option value="DICT_4X4_1000">1,000 unique IDs · 0–999</option></select></label>
 <p className="hint">{project.markers.length} markers placed. Configure the physical detector to use the same dictionary.</p>
 <div className="dimensions"><Field label="Marker ID" value={markerId} onChange={setMarkerId} min={0} max={project.dictionary === 'DICT_4X4_1000' ? 999 : 49} step={1} /><Field label="Side · m" value={markerSize} onChange={setMarkerSize} min={.01} max={1} /></div><div className="marker-preview"><img src={`/api/markers/${markerId}.png?dictionary=${project.dictionary}`} alt={`ArUco marker ${markerId}`} /><div><strong>{project.dictionary}</strong><small>ID {markerId} · {markerSize * 1000} mm</small><a href={`/api/markers/${markerId}.png?dictionary=${project.dictionary}`} download={`marker-${markerId}.png`}>Download PNG ↗</a></div></div><label className="field">Print layout<select aria-label="Markers per page" value={markersPerPage} onChange={e => setMarkersPerPage(Number(e.target.value) as 1 | 2 | 4)}><option value={1}>1 marker per page</option><option value={2}>2 markers per page</option><option value={4}>4 markers per page</option></select></label><p className="hint">Large markers are scaled to fit the chosen layout; the PDF labels the actual printed size.</p><button className="full" disabled={busy || !project.markers.length} onClick={() => void task(async () => download(await (await requestFile('/api/markers/pdf', {...project, markers_per_page: markersPerPage})).blob(), 'kenny-markers.pdf'))}>Print placed markers</button></div></aside>
 <main><div className="canvas-toolbar"><div><span className="status-dot" /> {viewLive ? 'LIVE ROOM SCAN' : 'MAP EDITOR'} <span className="muted">/ {project.name}</span></div><div><button disabled={!history.length || viewLive} onClick={undo} title="Undo">↶</button><button disabled={!future.length || viewLive} onClick={redo} title="Redo">↷</button><label><input type="checkbox" checked={snap} onChange={e => setSnap(e.target.checked)} /> Snap 10 cm</label></div></div>
 {message && <div role="status" className="notice">{message}<button onClick={() => setMessage('')}>×</button></div>}
 {calibrating && <div className="calibration"><strong>Calibrate floor plan · {calPoints.length}/2 points</strong><Field label="Actual distance · m" value={realDistance} onChange={setRealDistance} min={.01} /><button disabled={calPoints.length !== 2} onClick={calibrate}>Apply scale</button><button onClick={() => {
            setCalibrating(false);
            setCalPoints([]);
          }}>Cancel</button></div>}
 {replay && <div className="replay-controls"><button onClick={() => {
            if (!playing && nearSoundEnabled) void nearAnnouncement.current!.enable().catch(() => setMessage('Audio could not be enabled.'));
            if (frameIndex === replay.frames.length - 1) setFrameIndex(0);
            setPlaying(v => !v);
          }}>{playing ? 'Pause' : 'Play'}</button><input aria-label="Replay position" type="range" min="0" max={replay.frames.length - 1} value={frameIndex} onChange={e => {
            setPlaying(false);
            setFrameIndex(Number(e.target.value));
          }} /><span>{(frameIndex * replay.dt).toFixed(1)} / {((replay.frames.length - 1) * replay.dt).toFixed(1)} s</span><select aria-label="Playback speed" value={playSpeed} onChange={e => setPlaySpeed(Number(e.target.value))}><option value={1}>1×</option><option value={2}>2×</option><option value={5}>5×</option></select><button onClick={() => {
            setReplay(null);
            setPlaying(false);
            nearAnnouncement.current!.reset();
          }}>Close</button></div>}
 <div className="canvas-wrap"><svg ref={svg} role="img" aria-label="Editable environment map" viewBox={`${(W - vW) / 2 + pan[0]} ${(H - vH) / 2 + pan[1]} ${vW} ${vH}`} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={pointerUp} onWheel={e => setZoom(z => Math.max(.25, Math.min(8, z * (e.deltaY < 0 ? 1.1 : .9))))} onDragOver={e => e.preventDefault()} onDrop={e => {
            e.preventDefault();
            add(e.dataTransfer.getData('text/kenny-tool'), world(e));
          }} style={{
            cursor: calibrating ? 'crosshair' : tool === 'pan' ? 'grab' : tool === 'select' ? 'default' : 'crosshair'
          }}>
 <defs><pattern id="grid" width=".5" height=".5" patternUnits="userSpaceOnUse"><path d="M .5 0 H 0 V .5" fill="none" stroke="#afc6bd" strokeWidth=".009" /></pattern></defs><rect x={-.04} y={-.04} width={W + .08} height={H + .08} fill="#b4c9be" rx=".02" /><image href={image} width={W} height={H} style={{
              imageRendering: 'pixelated'
            }} />
 {!viewLive && project.background && <image href={project.background.data} width={project.background.width} height={project.background.height} opacity={opacity} preserveAspectRatio="none" />}<rect width={W} height={H} fill="url(#grid)" opacity=".5" pointerEvents="none" />
 {!viewLive && project.obstacles.map(o => {
              const points = [[o.x, o.y], [o.x + o.width, o.y], [o.x + o.width, o.y + o.depth], [o.x, o.y + o.depth]].map(visual);
              return <g key={o.uid} data-kind="obstacle" data-uid={o.uid}><polygon points={points.map(p => p.join(',')).join(' ')} className={`map-obstacle ${o.kind} ${selected?.uid === o.uid ? 'chosen' : ''}`} /><text x={points[0][0] + .1} y={points[0][1] - .1} fontSize=".13" fill="#47565e">{o.kind === 'prohibited' ? 'NO GO' : o.kind.toUpperCase()}</text>{selected?.uid === o.uid && <rect x={points[2][0] - .06} y={points[2][1] - .06} width=".12" height=".12" fill="#0b8b69" onPointerDown={e => {
                  e.stopPropagation();
                  const before = project,
                    initial = world(e);
                  const element = e.currentTarget;
                  element.setPointerCapture(e.pointerId);
                  const move = (evt: PointerEvent) => {
                    const p = world(evt);
                    setProject({
                      ...before,
                      obstacles: before.obstacles.map(b => b.uid === o.uid ? {
                        ...b,
                        width: Math.max(.05, o.width + p[0] - initial[0]),
                        depth: Math.max(.05, o.depth + p[1] - initial[1])
                      } : b)
                    });
                  };
                  const up = () => {
                    setHistory(h => [...h.slice(-29), before]);
                    setFuture([]);
                    element.removeEventListener('pointermove', move);
                    element.removeEventListener('pointerup', up);
                    element.removeEventListener('pointercancel', up);
                  };
                  element.addEventListener('pointermove', move);
                  element.addEventListener('pointerup', up);
                  element.addEventListener('pointercancel', up);
                }} />}</g>;
            })}
 {!viewLive && replayFrame?.sensors && <SensorOverlay sensors={replayFrame.sensors} visual={visual} lidar={showLidar} depth={showDepth} floor={showFloor} />}
 {!viewLive && showMarkers && replayFrame?.camera_visible_marker_ids && <g pointerEvents="none" aria-label="Camera-visible ArUco markers">{project.markers.filter(m => replayFrame.camera_visible_marker_ids!.includes(m.id)).map(m => {
   const p=visual([m.x,m.y]);
   return <g key={m.uid}><circle cx={p[0]} cy={p[1]} r={Math.max(.3,m.size/2+.15)} fill="#4ade80" opacity=".3" /><circle cx={p[0]} cy={p[1]} r={Math.max(.3,m.size/2+.15)} fill="none" stroke="#16a34a" strokeWidth=".05" /></g>;
 })}</g>}
 {!viewLive && project.markers.map(m => {
              const p = visual([m.x, m.y]),
                s = Math.max(.3, m.size);
              return <g key={m.uid} data-kind="marker" data-uid={m.uid} transform={`translate(${p[0]},${p[1]})`}><g transform={`rotate(${-(m.yaw - grid.origin[2]) * 180 / Math.PI})`}><rect x={-s / 2 - .04} y={-s / 2 - .04} width={s + .08} height={s + .08} rx=".025" fill={selected?.uid === m.uid ? '#0b8b69' : '#fff'} stroke="#0b8b69" strokeWidth=".015" /><image href={`/api/markers/${m.id}.png?dictionary=${project.dictionary}`} x={-s / 2} y={-s / 2} width={s} height={s} /><path d={`M 0 ${-s / 2 - .06} l -.04 .07 h .08 Z`} fill="#0b8b69" /></g><text y={s / 2 + .2} textAnchor="middle" fontSize=".15" fill="#11694f">ID {m.id} · {m.mount}</text></g>;
            })}
 {!viewLive && (['start', 'goal'] as const).filter(k => k === 'start' || project.destination_marker_id != null).map(k => {
              const p = visual(project[k]);
              return <g key={k} data-kind={k} data-uid={k} transform={`translate(${p[0]},${p[1]})`}><circle r={k === 'start' ? .19 : .25} fill={k === 'start' ? '#198e71' : 'none'} stroke={k === 'start' ? 'white' : '#eea247'} strokeWidth=".04" pointerEvents={k === 'goal' ? 'visibleStroke' : 'auto'} />{k === 'start' && <text y=".05" textAnchor="middle" fontSize=".15" fill="white">K</text>}<text y={k === 'start' ? .4 : .6} textAnchor="middle" fontSize=".15" fill="#47565e">{k === 'start' ? 'KENNY' : `DESTINATION · ID ${project.destination_marker_id}`}</text></g>;
            })}
 {!viewLive && replayFrame && replay && <g pointerEvents="none"><polyline points={replayFrame.route.map(visual).map(p => p.join(',')).join(' ')} fill="none" stroke="#5a8fc7" strokeWidth=".035" strokeDasharray=".1 .06" /><polyline points={replay.frames.slice(0, frameIndex + 1).map(f => visual(f.pose).join(',')).join(' ')} fill="none" stroke="#0b996f" strokeWidth=".045" />{(() => {
                const p = visual(replayFrame.pose),
                  estimated = visual(replayFrame.estimate);
                return <><circle cx={estimated[0]} cy={estimated[1]} r={replay.robot_radius + .03} fill="none" stroke="#c266aa" strokeWidth=".02" strokeDasharray=".04 .03" /><g transform={`translate(${p[0]},${p[1]}) rotate(${-(replayFrame.pose[2] - grid.origin[2]) * 180 / Math.PI})`}><circle r={replay.robot_radius} fill={replayFrame.intervened ? '#e5982c' : '#0b996f'} stroke="white" strokeWidth=".025" /><path d={`M ${replay.robot_radius + .1} 0 l -.1 -.065 v .13 Z`} fill="#0b996f" /></g></>;
              })()}</g>}
 {viewLive && live?.pose && (() => {
              const p = visual(live.pose);
              return <g transform={`translate(${p[0]},${p[1]}) rotate(${-(live.pose[2] - grid.origin[2]) * 180 / Math.PI})`}><circle r=".2" fill="#119b78" /><path d="M .32 0 L .14 -.1 L .14 .1 Z" fill="#119b78" /></g>;
            })()}
 {calPoints.map((p, i) => <circle key={i} cx={p[0]} cy={H - p[1]} r=".08" fill="#e79937" />)}
 </svg><div className="zoom-controls"><button onClick={() => setZoom(z => Math.max(.25, z / 1.2))}>−</button><span>{Math.round(zoom * 100)}%</span><button onClick={() => setZoom(z => Math.min(8, z * 1.2))}>＋</button><button onClick={() => {
              setZoom(1);
              setPan([0, 0]);
            }}>Fit</button></div><div className="map-legend"><span><i className="free" />Free</span><span><i className="occupied" />Occupied</span><span><i className="unknown" />Unknown</span><span><i className="no-go" />No-go</span></div></div>
 <footer><span>{W.toFixed(2)} × {H.toFixed(2)} m <b>·</b> {grid.resolution * 100} cm / cell</span><span>{project.markers.length} markers <b>·</b> {project.obstacles.length} obstacles <b>·</b> Frame: map</span></footer></main>
 <aside className="right"><div className="section-heading">OBJECT PROPERTIES</div>{chosen ? <><h2>{selected?.kind === 'marker' ? `ArUco marker ${(chosen as Marker).id}` : `${(chosen as Obstacle).kind}`}</h2><p className="hint">Position in meters in the map frame.</p><div className="dimensions"><Field label="X · m" value={chosen.x} onChange={v => change('x', v)} /><Field label="Y · m" value={chosen.y} onChange={v => change('y', v)} /></div>{selected?.kind === 'marker' ? <><Field label="Marker ID" value={(chosen as Marker).id} onChange={v => change('id', v)} min={0} max={project.dictionary === 'DICT_4X4_1000' ? 999 : 49} step={1} /><Field label="Printed side · m" value={(chosen as Marker).size} onChange={v => change('size', v)} min={.01} max={1} /><label className="field">Mounting<select value={(chosen as Marker).mount} onChange={e => {
                const mount = e.target.value;
                commit({
                  ...project,
                  ...((chosen as Marker).id === project.destination_marker_id ? {
                    destination_offset_m: mount === 'wall' ? .5 : 0
                  } : {}),
                  markers: project.markers.map(m => m.uid === selected.uid ? {
                    ...m,
                    mount: mount as Marker['mount'],
                    z: mount === 'wall' ? 1 : 0
                  } : m)
                });
              }}><option value="floor">Floor</option><option value="wall">Wall</option></select></label><Field label="Height Z · m" value={(chosen as Marker).z} onChange={v => change('z', v)} min={0} /><Field label="Facing / rotation · degrees" value={Math.round((chosen as Marker).yaw * 180 / Math.PI)} onChange={v => change('yaw', v * Math.PI / 180)} step={1} /></> : <><div className="dimensions"><Field label="Width · m" value={(chosen as Obstacle).width} onChange={v => change('width', v)} min={.05} /><Field label="Depth · m" value={(chosen as Obstacle).depth} onChange={v => change('depth', v)} min={.05} /></div><Field label="Bottom elevation · m" value={(chosen as Obstacle).bottom} onChange={v => change('bottom', v)} min={0} /><Field label="Object height · m" value={(chosen as Obstacle).height} onChange={v => change('height', v)} min={.01} /></>}{selected?.kind === 'marker' && <button className="full primary" onClick={() => chooseDestination((chosen as Marker).id)}>Use marker as destination</button>}<button className="danger full" onClick={remove}>Delete object</button></> : selected && (selected.kind === 'start' || selected.kind === 'goal') ? <><h2>{selected.kind === 'start' ? 'Robot start' : `Destination · ID ${project.destination_marker_id}`}</h2>{selected.kind === 'goal' ? <p className="hint">Arrival point: ({project.goal[0].toFixed(2)}, {project.goal[1].toFixed(2)}) m. Move the marker or adjust its approach offset to change this point.</p> : [0, 1].map(i => <Field key={i} label={`${i === 0 ? 'X' : 'Y'} · m`} value={project[selected.kind as 'start' | 'goal'][i]} onChange={v => {
            const p = [...project[selected.kind as 'start' | 'goal']];
            p[i] = v;
            commit({
              ...project,
              [selected.kind]: p
            });
          }} />)}</> : <div className="empty-properties"><span>↖</span><strong>Select an object</strong><p>Click a marker or obstacle to edit its position and dimensions.</p></div>}
 {project.background && <label className="field separated">Floor plan opacity<input type="range" min="0" max="1" step=".05" value={opacity} onChange={e => setOpacity(Number(e.target.value))} /></label>}
 <div className="navigation-panel"><div className="section-heading">SENSOR VISUAL GUIDE</div>
 <label className="sound-toggle"><input type="checkbox" checked={showLidar} onChange={e=>setShowLidar(e.target.checked)} /> LiDAR rays / hits · blue</label>
 <label className="sound-toggle"><input type="checkbox" checked={showDepth} onChange={e=>setShowDepth(e.target.checked)} /> RGB-D depth / camera field of view · purple</label>
 <label className="sound-toggle"><input type="checkbox" checked={showFloor} onChange={e=>setShowFloor(e.target.checked)} /> Floor hazard scan · yellow</label>
 <label className="sound-toggle"><input type="checkbox" checked={showMarkers} onChange={e=>setShowMarkers(e.target.checked)} /> Camera-visible ArUcos · green glow</label>
 <p className="hint">Dots: recorded hits. Dashed red: invalid readings, not obstacles. Purple fan: nominal camera field of view, not guaranteed visibility. Scans are projected from the estimated acquisition pose.</p>
 <p className="hint">Green markers pass geometric range, horizontal/vertical FOV, mounting-face and occlusion checks. This is not decoded RGB detection. The localization simulator uses a simpler marker model.</p>
 {!replayFrame && <p className="hint">Run a navigation test to record sensor readings. These controls affect replay display only, not robot commands.</p>}
 {replayFrame && !replayFrame.sensors && <p className="hint">This older replay has no sensor data. Run a new test after updating the simulator.</p>}
 {replayFrame?.sensors && <div className="hint">LiDAR valid: {Math.round(replayFrame.sensors.lidar.valid.filter(Boolean).length/replayFrame.sensors.lidar.valid.length*100)}% · sample age: {replayFrame.sensors.lidar.age_steps} steps<br />Depth valid: {Math.round(replayFrame.sensors.depth.valid.filter(Boolean).length/replayFrame.sensors.depth.valid.length*100)}%<br />Floor valid: {Math.round(replayFrame.sensors.floor.valid.filter(Boolean).length/replayFrame.sensors.floor.valid.length*100)}%<br />Guard: {replayFrame.guard_reasons?.join(', ') || 'clear'}<br />Visible marker IDs: {replayFrame.camera_visible_marker_ids?.join(', ') || 'none'}<br />Localization update: {replayFrame.marker_localization_updated ? 'yes' : 'no'}</div>}
 </div>
 <div className="navigation-panel"><div className="section-heading">SELECTED CHECKPOINT</div>
 <strong>{selectedModel ? modelLabel(selectedModel) : 'No model selected'}</strong>
 <p style={{overflowWrap:'anywhere',fontFamily:'monospace',fontSize:12}}>{selectedModel}</p>
 <p className="hint">This is the selected checkpoint, not a controller-mode selector. Marker sweep is not automatically enabled.</p>
 {replay && <><strong>Displayed replay checkpoint</strong><p style={{overflowWrap:'anywhere',fontSize:12}}>{replay.model}</p></>}
 </div>
 <div className="navigation-panel"><div className="section-heading">CALL KENNY · SIMULATION</div>
 <h2>Nearest caller queue</h2><p className="hint">Calls wait until the current trip finishes. Ranking uses straight-line arrival distance, not route length. After 5 minutes, oldest waiting calls take priority. Session-only queue; map edits clear it. This does not send commands to a physical robot.</p>
 <label className="field">Caller name<input maxLength={80} value={callerName} onChange={e => setCallerName(e.target.value)} placeholder="Student / desk name" /></label>
 <label className="field">Caller location<select value={callerMarker} onChange={e => setCallerMarker(e.target.value)}><option value="">Choose an ArUco location…</option>{project.markers.map(m => <option key={m.uid} value={m.id}>ArUco ID {m.id}</option>)}</select></label>
 <button className="full" disabled={!callerName.trim() || callerMarker === '' || viewLive} onClick={() => {
   const markerId = Number(callerMarker), caller = callerName.trim();
   if (!project.markers.some(m => m.id === markerId)) return;
   if (calls.some(c => c.caller.toLowerCase() === caller.toLowerCase())) { setMessage('This caller already has a waiting request.'); return; }
   setCalls(waiting => [...waiting, { id: newUid(), caller, markerId, createdAt: Date.now() }]);
   setCallerName('');
 }}>Call Kenny</button>
 {activeCall && <p role="status">Serving {activeCall.caller} · ID {activeCall.markerId}. New calls will wait.</p>}
 <p className="hint">Queue origin: {dispatchPosition ? 'last simulated position' : 'robot start'}. Wall arrivals use a 0.5 m offset.</p>
 <ol>{rankCalls(project, calls, dispatchPosition ?? project.start, Date.now()).map(c => <li key={c.id}>
   {c.caller} · ID {c.markerId} · {c.distance.toFixed(2)} m{c.overdue ? ' · waiting priority' : ''}
   <button disabled={activeCall?.id === c.id} onClick={() => setCalls(waiting => waiting.filter(item => item.id !== c.id))}>Cancel</button>
 </li>)}</ol>
 <button className="full primary" disabled={testing || playing || !selectedModel || viewLive || calibrating || calls.length === 0} onClick={() => {
   const next = rankCalls(project, calls, dispatchPosition ?? project.start, Date.now())[0];
   if (next) void runNavigation(next);
 }}>Serve nearest waiting caller</button>
 <button className="full" disabled={testing} onClick={() => { setCalls([]); setDispatchPosition(null); }}>Clear queue / reset position</button>
 </div>
 <div className="navigation-panel"><div className="section-heading">TEST NAVIGATION</div><h2>Watch your model navigate</h2><p className="hint">Use your current map, robot start, and destination. This runs your trained PPO checkpoint in Kenny’s simulator.</p><label className="field">Destination marker<select aria-label="Destination marker" value={project.destination_marker_id ?? ''} onChange={e => {
              if (e.target.value === '') {
                commit({
                  ...project,
                  destination_marker_id: null
                });
                return;
              }
              chooseDestination(Number(e.target.value));
            }}><option value="">Choose an ArUco marker…</option>{project.markers.map(m => <option key={m.uid} value={m.id}>ArUco ID {m.id} · {m.mount}</option>)}</select></label>{project.destination_marker_id != null && project.markers.find(m => m.id === project.destination_marker_id)?.mount === 'wall' && <Field label="Approach offset from wall · m" value={project.destination_offset_m ?? .5} min={.25} max={2} onChange={v => commit({
            ...project,
            destination_offset_m: v
          })} />}<p className="hint">{project.destination_marker_id == null ? 'Place markers and choose your destination before running or exporting.' : `Navigate to ArUco ID ${project.destination_marker_id}. The destination stays attached to this marker.`}</p><label className="sound-toggle"><input type="checkbox" checked={nearSoundEnabled} onChange={e => {
              setNearSoundEnabled(e.target.checked);
              if (e.target.checked) void nearAnnouncement.current!.enable().catch(() => setMessage('Audio could not be enabled.'));else nearAnnouncement.current!.silence();
            }} /> Play “I’m near” within 5 meters</label>
 <label className="field">Trained model<select aria-label="Trained model" title={selectedModel} value={selectedModel} onChange={e => {setSelectedModel(e.target.value);setReplay(null);setPlaying(false);nearAnnouncement.current!.reset();}} disabled={testing}>{modelChoices.map(m => <option key={m.id} value={m.id}>{modelLabel(m.id)}</option>)}</select></label>
 <p className="hint" style={{overflowWrap:'anywhere'}}><strong>Checkpoint:</strong> {selectedModel}</p>
 {modelError && <p className="hint">{modelError}</p>}<div className="dimensions"><Field label="Max steps" value={testSteps} onChange={setTestSteps} min={1} max={3000} step={100} /><Field label="Random seed" value={testSeed} onChange={setTestSeed} min={0} max={4294967295} step={1} /></div><button className="full primary" disabled={testing || !selectedModel || viewLive || calibrating || project.destination_marker_id == null} onClick={() => void runNavigation()}>{testing ? 'Running model…' : '▶ Run navigation test'}</button>{replay && <div className="test-result"><strong className={`outcome ${replay.info.event}`}>{replay.info.event === 'success' ? 'Destination reached' : replay.info.event === 'timeout' ? 'Time limit reached' : replay.info.event}</strong><div>Distance: {replay.info.path_length.toFixed(2)} m</div><div>Safety interventions: {replay.info.interventions}</div><div>Steps without a route: {replay.info.no_route_steps}</div><div>Localization error: {replay.info.localization_error.toFixed(3)} m</div><p className="hint">Green: traveled path · dashed blue: current planned route · purple: estimated pose · orange robot: safety guard intervention.</p>{replayFrame && <div className={`proximity ${replayFrame.near_goal ? 'near' : ''}`}>{replayFrame.near_goal ? 'I’m near · ' : ''}{replayFrame.distance_to_destination_m.toFixed(2)} m to destination{replay.destination_marker_id != null ? ` · ID ${replay.destination_marker_id}` : ''}</div>}{replayFrame && <div className="hint">Step {replayFrame.step} · {replayFrame.intervened ? 'Safety guard active' : replayFrame.event}</div>}<button className="full" onClick={() => download(new Blob([JSON.stringify(replay, null, 2)], {
              type: 'application/json'
            }), 'kenny-navigation-replay.json')}>Download test result</button></div>}</div>
 <div className="mapping-panel"><div className="section-heading">KENNY LIVE MAPPING</div><h2>Scan your environment</h2><p className="hint">Move Kenny with its manual controls. Capture the scanned map when you’re ready to edit.</p><label className="field">Mapping bridge URL<input value={bridge} onChange={e => setBridge(e.target.value)} placeholder="Same server, or ws://kenny:8000/api/live" /></label><div className="connection"><span className={`status-dot ${connection === 'Connected' && !stale ? '' : 'offline'}`} />{connection === 'Connected' && stale ? 'Connected · map stale' : connection}</div><div className="dimensions"><button onClick={connect}>Connect</button><button onClick={() => {
              socket.current?.close();
              setConnection('Disconnected');
              setViewLive(false);
            }}>Disconnect</button></div>{live && <button className="full secondary" onClick={() => {if(!viewLive){setPlaying(false);nearAnnouncement.current!.silence();}setViewLive(v => !v);}}>{viewLive ? 'Return to editor' : 'View live scan'}</button>}<button className="full primary" disabled={!live || stale || connection !== 'Connected'} onClick={capture}>Capture map for editing</button><small className="hint">Unknown space stays blocked in Kenny’s guide.</small></div><div className="export-tip"><b>Ready for the real world</b><p>Print markers at their specified size and install them at their mapped positions before using the environment.</p></div></aside></div></div>;
}
function Field({
  label,
  value,
  onChange,
  min,
  max,
  step = .05
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  const format = (v: number) => Number.isFinite(v) ? String(Math.round(v * 10000) / 10000) : '';
  const [text, setText] = useState(() => format(value));
  useEffect(() => setText(format(value)), [value]);
  function commit() {
    const next = Number(text);
    if (Number.isFinite(next) && (min === undefined || next >= min) && (max === undefined || next <= max)) onChange(next);else setText(format(value));
  }
  return <label className="field">{label}<input type="number" value={text} min={min} max={max} step={step} onChange={e => {
      const next = e.target.value;
      setText(next);
      const number = Number(next);
      if (Number.isFinite(number) && (min === undefined || number >= min) && (max === undefined || number <= max)) onChange(number);
    }} onBlur={commit} onKeyDown={e => {
      if (e.key === 'Enter') e.currentTarget.blur();
      if (e.key === 'Escape') {
        setText(format(value));
        e.currentTarget.blur();
      }
    }} /></label>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
