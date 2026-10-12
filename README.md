# Kenny Environment Studio

## Map → ESP32 USB on this device

Open **Kenny Map Editor** on the desktop or **http://localhost:8000/**. Run a
navigation test, then select **Drive ESP32 with this map** to stream its recorded
movement commands to the physical robot. No physical sensors are required for
this open-loop test. See [USB map drive](docs/USB_MAP_DRIVE.md) for startup,
motor power, STOP behavior and the distinction between simulated and physical pose.

Navigation tests default to **Route recovery + marker sweep**, with an 1800-step limit. The controller selector also offers checkpoint settings for baseline comparisons. Recovery uses the existing planned route and keeps the safety shield enabled; it is not a guarantee of safe physical deployment. Replay results record the controller and enabled recovery flags. Rerun a test after changing modes. Update the sibling simulator repository along with this editor.

A local browser editor for Kenny’s environment maps, printable ArUco landmarks, and obstacles. Start from a blank measured grid, a floor-plan image, a saved ROS map, or a live ROS scan. Download a reusable project or a robot/simulator export bundle.

## Run on this workstation

The frontend is built in `dist/`, and this workstation already has the Python dependencies needed by the lightweight server:

```sh
cd /home/kenny/kenny-map-creator
../Kenny---Automotive-self-driving-trash-can/.venv/bin/python backend/server.py
```

Open **http://localhost:8000**. Stop the server with Ctrl+C.

The lightweight server and FastAPI adapter share exactly the same marker, import, export, and validation services. The lightweight adapter allows running offline without FastAPI; the production adapter uses FastAPI/Uvicorn.

## Fresh installation and development

Use Node.js 22.12+ and Python 3.10–3.12, matching the existing Kenny simulator. Keep the editor and `Kenny---Automotive-self-driving-trash-can` directories beside each other.

```sh
cd kenny-map-editor
npm ci
npm run build
python3.10 -m venv .venv
cd backend
../.venv/bin/python -m pip install -r requirements.txt
cd ..
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

For frontend development run `npm run dev` in another terminal. Vite proxies `/api` and its WebSocket to port 8000. This is a local application; no accounts or cloud service are required. Only bind to `0.0.0.0` when access from another device on your trusted robot network is needed.

## Editing and printing

### Render map and ArUco position tools

In the right sidebar, **Upload map to Render** saves your current environment
to `https://kenny-api.onrender.com`. **Fetch map from Render** displays the actual
stored geometry and markers with its revision/hash in a read-only preview.
**Open fetched map in editor** opens it with Undo support, and the download
button saves `environment.json`. The API stores uploaded maps on its persistent
SQLite disk. Finish pending/running calls before replacing the active map.
These controls require the updated `Kenny-Api` map endpoints to be deployed;
`KENNY_API_URL` and `KENNY_PI_TOKEN` configure the local editor proxy if needed.

**Optimize ArUco positions** suggests nearby positions that improve potential
line-of-sight coverage from robot-reachable free floor samples. It accounts for
occupied/unknown-cell occlusion, wall-marker facing direction, arrival clearance,
marker spacing, and nominal camera vertical field of view. Configure the maximum
3D movement, spacing, and camera height; select all markers or only the selected
one. Wall heights change only when the corresponding checkbox is enabled.

Click **Preview optimized ArUco positions** to show purple suggestions without
changing the map, then **Apply optimized positions** or **Discard suggestions**.
Apply is undoable and keeps IDs, printed sizes, and mounting types. Suggestions
clear when the map changes. Install/survey any moved physical markers at their
new positions before navigation, then upload the updated map to Render. The
reported coverage is a bounded geometric estimate, not measured detector accuracy.

While the API receiver is enabled, simulation playback publishes its estimated
position to the mobile live map once per second, labeled **SIMULATED**. Disable
the simulation receiver when the physical main controller is the pose source.

For more than 50 unique landmarks, select **1,000 unique IDs · 0–999**
under **Marker dictionary**. Existing projects default to `DICT_4X4_50`;
upgrading uses `DICT_4X4_1000` throughout PNG previews, print PDFs, map exports
and the simulator importer. OpenCV's first 50 patterns are identical in these
two dictionaries. Set the physical detector to the exported dictionary; do not
mix undocumented dictionaries. Switching back is blocked while IDs above 49
remain. Marker placement automatically advances to the next unused ID.
More markers alone do not guarantee visibility in every camera direction.

1. Set room dimensions and choose **New blank map**, or **Upload floor plan**. For a floor plan, select two distinct points and enter their measured distance; then trace its walls. A floor-plan image alone does not become navigation geometry.
2. Drag items from the palette or select a tool and click the map. Drag existing items to move them. Select an obstacle to resize it with its green corner handle or properties. Use the Pan tool, mouse wheel, or Fit button to move around the map.
3. Generate a marker using its ID and physical side length. Place each ID once. Select a marker to set floor/wall mounting, height, and orientation.
4. Place **Robot start** in free space and choose the destination’s ArUco ID under **Test navigation**, or select a marker and press **Use marker as destination**. The arrival point follows marker edits. Floor markers use their center; wall markers default to an approach point 0.5 m in front of their facing direction, with an adjustable offset. Export validation uses the existing simulator’s default robot dimensions.
5. Download marker PNGs or print the placed markers as a PDF. Choose **1, 2, or 4 markers per page** and print at **100% actual size**, disabling “fit to page.” Each A4 sheet contains complete markers—no cutting and assembling tiles. If a marker must shrink to fit the chosen layout, its actual printed black-square size is shown beneath it; use that measured size in the robot detector.
6. **Save project** downloads a ZIP that includes the floor plan; browser autosave is also available. **Open project** accepts these ZIPs, exported ZIPs, or environment JSON files. Downloaded projects are the durable backup if browser storage is full or cleared.
7. **Export for Kenny** creates a ZIP containing `environment.json`, `map.yaml`, `map.pgm`, `markers.yaml`, marker PNGs, and a vector print PDF.

The occupancy image preserves occupied, free, and unknown cells. Hand-placed obstacles and no-go areas become blocked navigation cells. Markers never become collision obstacles. Obstacles are axis-aligned in the map frame; markers can rotate. Unknown areas stay blocked when loaded into Kenny’s simulator.

Floor markers use OpenCV marker x-right, y-up, z-out-of-face, with the unrotated face pointing upward and its top along map +y. Wall markers have their top pointing along map +z; their facing angle is the outward normal’s angle from map +x, counterclockwise. Positions are marker centers, in meters. Install markers at their surveyed positions and use the matching dictionary and physical black-square dimensions in the robot detector.

## Live mapping with Kenny

The robot setup targets the existing project’s Raspberry Pi 5, YDLIDAR X3 Pro, and ROS 2 Jazzy. Scanning uses LiDAR SLAM and wheel odometry; the Astra camera is not required to build this 2D map.

Before starting the supplied launch:

- Run Kenny’s working LiDAR driver publishing `/scan` (`sensor_msgs/LaserScan`).
- Run wheel odometry publishing `/odom` and the `odom -> base_link` transform.
- Publish the measured `base_link -> LiDAR frame` transform.
- Verify timestamps and TF connectivity. Sensor drivers, encoder firmware, and calibration are hardware-specific prerequisites; the repository’s planned hardware stack is not replaced by this editor.

On the robot, with ROS sourced and Python dependencies installed:

```sh
source /opt/ros/jazzy/setup.bash
# On an Ubuntu machine where the package is not yet installed:
sudo apt install ros-jazzy-slam-toolbox
# Edit ros/slam.yaml for your actual frame names and scan topic.
ros2 launch /absolute/path/kenny-map-editor/ros/mapping.launch.py
```

The launch includes SLAM Toolbox’s official Jazzy asynchronous launch so its lifecycle is configured and activated, and starts the bridge on port 8000. The default frame is `map`. If SLAM already runs, start only the bridge:

```sh
python3 ros/bridge.py --host 0.0.0.0 --map-topic /map --base-frame base_link
```

Open the editor served by the robot at `http://ROBOT_IP:8000`, or enter `ws://ROBOT_IP:8000/api/live` in an editor served elsewhere. An HTTPS page needs a `wss://` bridge through an appropriate TLS proxy. Press **Connect** and drive using Kenny’s existing manual controls. The bridge streams occupancy and pose; it does not publish motor commands. **Capture map for editing** freezes the map. Further scan updates cannot overwrite that editable snapshot. A stale map disables capture, and missing/stale TF removes the robot indicator.

Keep SLAM as the sole publisher of `map -> odom` while mapping. When switching to navigation, stop mapping before starting the localization system that owns that transform. Capturing an occupancy map does not save SLAM’s pose graph; use SLAM Toolbox’s serialization service separately if you need to resume SLAM.

To exercise the connection before hardware is available:

```sh
python3 ros/bridge.py --fixture fixtures/sample-room.json
```

This serves a clearly named sample room without ROS. It is replay data, not a physical scan.

## Test your trained model inside the editor

For the physical, continuously mapping **main controller**, see the sibling
[`Kenny-Api/controller/README.md`](../Kenny-Api/controller/README.md). Export this
editor's map as an estimated prior. The resident controller replaces observed
geometry with SLAM evidence, corrects observed landmarks, and can reroute to a
nearer pending call without restarting the policy or localization. Its refined
`/kenny/map` can be viewed/captured using this editor's ROS bridge.

### Receive calls from the deployed API

The **API receiver · Simulation** panel connects to
`https://kenny-api.onrender.com` through the local editor backend. Open your
map and choose a checkpoint and controller. The receiver starts waiting
automatically when the map has markers and a checkpoint is available. Use
**Disconnect API receiver** to pause, or **Connect API receiver** to resume.
Keep the page open. Scanner calls automatically select their ArUco destination,
run the model, play the replay, and report `succeeded` only for simulated arrival
(otherwise `failed`). The next call waits until playback reaches the end;
pausing playback holds the queue. Calls are claimed oldest-first from the cloud,
independently of the editor's local nearest-caller preview.

The editor warms the selected PPO checkpoint once when it is selected. A resident
simulator worker retains that policy for subsequent calls and navigation tests;
there is no per-call Python/Torch/model startup. Switching checkpoints replaces
the cached policy. Replay tests still compute an episode before displaying it;
the physical main controller instead runs a continuous sensor/control loop and
supports in-trip nearer-call preemption.

Start the editor as described above; rebuild with `npm run build` after updating
its source. The incoming ID is resolved to its location on the open editor map,
so simulation coordinates can differ from cloud/physical coordinates. The marker
must exist locally and its dictionary must match the call. The API must also
recognize that ID to accept a scanner submission. Stop any physical Pi receiver
while testing, since both consumers share the same cloud queue.

Each call starts from the last simulated position; changing map geometry resets
that position. The backend saves progress in `data/simulation-receiver.json`.
Result-upload failures retry without repeating a trip. A backend restart marks
an interrupted simulation failed before accepting another call. This receiver
does not drive USB or physical motors. `KENNY_API_URL` overrides the cloud URL;
set `KENNY_PI_TOKEN` in the backend environment if the API requires it.

### Toggleable sensor visual guide

Run a new navigation test, then enable LiDAR, RGB-D depth/FOV, floor scan,
or camera-visible ArUco highlights under **Sensor visual guide**. Play, pause,
and scrub the replay to inspect individual samples. Blue/purple/yellow dots
are recorded hits; dashed red rays are invalid readings, not obstacle hits.
The purple sector is nominal camera field of view, not proof of clear space.
LiDAR retains its estimated acquisition pose and sample age; other rays are
projected from their estimated acquisition pose. Controls only affect drawing.

ArUcos glow green when an offline geometric camera check passes configured
range, horizontal/vertical FOV, surveyed marker height, visible mounting face,
and obstacle occlusion. This is not decoded RGB detection: image resolution,
print quality and detector errors are not simulated. The existing localization
surrogate uses a simpler floor-marker model, so a glow does not itself imply a
localization correction; the sidebar reports corrections separately.
The RGB-D overlay is a top-down depth surrogate, not an RGB image or a full
3D point cloud. Old replays remain usable but require a new test for sensor data.

### Multiple-caller scheduler preview

The **Call Kenny · Simulation** panel accepts a caller name and an ArUco
location. Add several calls, select a checkpoint in Test navigation, then press
**Serve nearest waiting caller**. Ordering uses straight-line distance to each
arrival point from the robot start or last simulated position; walls can make
actual travel longer, and the guarded simulator decides whether a trip succeeds.
Wall-marker calls use a 0.5 m approach offset. Equal distances prefer older
requests; calls waiting at least five minutes take oldest-first priority.

New calls never interrupt a running trip. Successful calls leave the queue;
failed calls remain for inspection or cancellation. Finish or pause playback
before manually dispatching the next trip. Cancel waiting calls individually,
or clear the queue/reset position. Map edits clear the queue and invalidate
replays. Each simulated leg resets the sensor/localization episode at its start;
this is not continuous physical robot state across trips.

This is a browser-session simulation prototype, not a shared multi-phone
service, persistent dispatch backend, or physical motor-control integration.
Refreshing loses queued calls but retains the separately autosaved map.

Open your created map, place **Robot start**, and select an ArUco ID under **Destination marker**. In the right sidebar, select a checkpoint under **Test navigation** and press **Run navigation test**. The current unsaved map is sent directly to the simulator; exporting first is unnecessary.

The “I’m near” recording from `res/im near.mp3` plays once per test when the replay’s actual simulated position is within **5.0 meters horizontally** of the selected marker. It uses the physical marker position even when a wall marker has a separate arrival point. The sound toggle defaults on; Run/Play enables browser audio. Pausing, scrubbing backward, or leaving and re-entering the radius does not repeat a successful announcement. A new navigation test re-arms it. Changing the map or closing a replay stops the sound. Actual speaker playback still requires browser/device testing.

Open `fixtures/marker-destination-room.json` for an example with ArUco ID 12 selected as the wall destination. In a trained-model check, Kenny reached its approach point in 259 steps, and the replay recorded the actual distance to marker 12 for the five-meter announcement.

Choosing a destination marker is required in the editor before testing or exporting. Deleting it clears the selection, and changing its ID updates the selection. Legacy coordinate-only environment files remain supported by the simulator; select a marker after opening one in the editor. `navigation.yaml` and `audio/im-near.mp3` are now included in robot exports. The navigation metadata identifies the marker, arrival point, proximity reference, threshold, and recording path; the physical robot navigation application must consume those settings and play the recording on its speaker.

The dropdown lists local Kenny runs that have a checkpoint plus `config.json` and `contract.json`. It includes your dynamic, mixed, and static trained runs; choose the exact run you want to inspect. Incompatible observation/robot contracts produce an error rather than being played back with the wrong inputs. The test uses the checkpoint’s saved sensor and motion settings and its map mode, deterministic policy predictions, and an enabled safety guard.

Replay uses **Play/Pause**, a position slider, and 1×/2×/5× speed. Green is traveled motion, dashed blue is the current planner route, purple is the estimated robot position, and orange indicates a guard intervention. Results show destination arrival, collision, cliff, or timeout, along with distance, intervention count, and steps without a route. Download the replay JSON to retain the result. Editing the map clears the old replay; edits during a running test require a new test.

Default limit is 1,200 steps; at 0.1 seconds/step this is 120 simulated seconds. Increase it up to 3,000 for longer routes. A timeout means the robot did not arrive within that budget. It can result from a blocked route, slow movement, or repeated interventions; inspect the replay and reported counts.

The backend runs the checkpoint using the existing simulator’s `.venv/bin/python`. If your trained-model environment lives elsewhere, start the server with:

```sh
KENNY_SIM_PYTHON=/absolute/path/to/python python3 backend/server.py
```

That Python environment needs the simulator, Torch, and Stable Baselines3 (`pip install -e '.[train]'` from the simulator directory). Tests run on CPU, one at a time, with a 180-second wall-clock limit. The preview is a 2D geometric simulation; physical robot behavior still depends on real sensor calibration and motion dynamics.

For command-line replay:

```sh
# From the simulator repository:
.venv/bin/python -m kenny_rl.replay \
  --environment /path/environment.json \
  --model runs/server-mixed-v3-planner-finetune/seed_3/best.zip \
  --steps 1200 --seed 42 --output replay.json
```

## Feed the export into Kenny

Unzip the exported bundle. From the simulator repository:

```sh
.venv/bin/python -m kenny_rl.demo \
  --environment /absolute/path/environment.json \
  --snapshot artifacts/my-environment.png

# With an existing trained checkpoint:
.venv/bin/python -m kenny_rl.evaluate \
  --model runs/YOUR_RUN/final.zip \
  --environment /absolute/path/environment.json \
  --episodes 10 --output artifacts/site-evaluation.json
```

The loader rotates/translates the ROS origin into local simulator coordinates and pads rectangular maps to the simulator’s square shape with blocked geometry. It retains original origin and marker metadata on the loaded world. Demo `--start`, `--goal`, and `--heading` overrides use **local simulator coordinates**, not original ROS world coordinates. Custom maps do not acquire randomly generated clutter during replay. Marker visibility remains the existing approximate simulation model, not camera-based detection.

For physical navigation, point Nav2’s map server at the exported `map.yaml`. `markers.yaml` is the application’s surveyed landmark database; it is **not** a Nav2 parameter file. The robot’s localization node must load its dictionary, sizes, positions, and quaternion orientations. Kenny’s documentation describes this node, but its physical implementation is separate work. Exporting a map does not install navigation firmware or automatically start robot motion.

## Interfaces and checks

`environment.json` version 1 uses `frame_id: map`, `units: meters`, `dictionary: DICT_4X4_50`, and `grid: {width, height, resolution, origin: [x,y,yaw], data}`. Grid data is ROS row-major, starting at the lower-left, with values `-1` (unknown), `0` (free), and `100` (occupied). `markers` contain `id, x, y, z, yaw, size, mount`; `obstacles` contain `kind, x, y, width, depth, bottom, height`. Obstacle x/y is its lower-left world-frame corner; size is horizontal extent and height is vertical extent above bottom. Start and goal contain world x/y. Optional `destination_marker_id` selects the authoritative landmark; `destination_offset_m` adjusts its arrival point along its facing direction. A chosen marker overrides stale saved goal coordinates. Editor objects also have a `uid`; background images are optional.

Navigation interfaces: `GET /api/models` lists available checkpoints; `POST /api/simulate` accepts `{environment, model, steps, seed}` and returns frames, timing, and episode results.

HTTP interfaces: `GET /api/markers/{id}.png`, `POST /api/markers/pdf`, `POST /api/export`, and `POST /api/import-map` (YAML text and base64 image). The WebSocket `/api/live` sends status messages or `{type: map, revision, grid, pose: [x,y,yaw] | null, map_age_seconds}`. Maps are limited to four million cells, and saved-map import supports trinary maps. Invalid exports return readable HTTP 422 errors.

```sh
npm test
python3 -m unittest discover -s tests -v
# From the existing simulator, using its environment:
.venv/bin/python -m pytest -q
```

The PDF rendering test needs Poppler’s `pdftoppm`. Tested here: frontend production build and coordinate/validation tests, marker detection, vector PDF rendering/detection, export/import round-trip, HTTP route handling without sockets, and all 92 simulator tests. Full browser interaction, FastAPI startup, ROS launch, and physical scanning still need checking on a machine that can run the server and robot stack.

Sample artifacts are in `artifacts/`: an exported environment ZIP, printable markers, a simulator preview, a trained-model replay JSON, and `sample-navigation.gif`. The mixed-stage seed 3 best checkpoint reached the sample room destination in 307 steps (30.7 simulated seconds), traveling 5.54 meters.

To turn a downloaded replay into a shareable animation:

```sh
python3 scripts/render_replay.py --environment /path/environment.json \
  --replay /path/kenny-navigation-replay.json --output navigation.gif
```
