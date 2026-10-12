# Run a map and drive Kenny over USB

This workstation has the updated Kenny Automotive simulator, your saved RL
checkpoint, the map editor and the ESP32 USB bridge. Physical sensors are not
needed for this **open-loop command playback**.

## Use it now

1. Open **Kenny Map Editor** on the desktop, or **http://localhost:8000/**.
2. Open your project/map. Place **Robot start** and select a destination marker.
   The marker is a map destination; no physical camera scan is needed here.
3. Select the trained model. Your existing model is
   `releases/dynamic-v3-seed2/model/best.zip`; the pulled faster-noise checkpoints
   are also listed.
4. Press **Run navigation test**. This runs the policy against your map and
   records the final movement targets, including simulated guard/recovery stops.
5. In **ESP32 USB · OPEN-LOOP MAP DRIVE**, choose motor power (default **70%**,
   matching your observed motor startup threshold)
   and press **Drive ESP32 with this map**.
6. The replay starts from the beginning at real-time **1×**, streaming USB V
   commands every 50 ms. The robot receives forward/turn commands whenever the
   recorded model command is nonzero. **STOP ROBOT** or Escape stops/disarms.

The controller sends STOP at completion, link failure, browser clock delays,
page hide/blur/close, replay replacement, or a recorded collision/cliff. The
firmware also disarms after 300 ms without fresh commands. Simulation Play,
scrubbing and 2×/5× preview controls do not drive motors. Do not leave another
Wi-Fi or joystick session armed when starting a map drive.

## Meaning of the displayed map

The RL policy still uses the simulator's map and simulated observations. Only
its final movement commands are forwarded to hardware. The displayed robot
position is simulated, not a measurement of the physical robot. This mode does
not detect real obstacles or correct physical drift.

Linear and angular requests are scaled together to the ESP32 limits (±0.10,
±0.60), then multiplied by the power setting. The existing breadboard firmware
maps these to PWM; they are not calibrated physical velocities. Lower power and
the firmware's direction-coast intervals change actual travel relative to the
replay. This is a functional map-to-motor test, not proof of physical arrival.

70% is a command scale, not a guaranteed minimum duty on each motor. Low model
targets and mixed turns can still fall below the observed startup threshold.
The setting does not add a minimum-duty boost or change STOP/zero commands.

## Restart manually

From `/home/kenny/joystick`:

```bash
python3 scripts/usb_bridge.py \
  --port /dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
```

From `/home/kenny/kenny-map-creator`:

```bash
../Kenny---Automotive-self-driving-trash-can/.venv/bin/python backend/server.py
```

Open **http://localhost:8000/**. Close Arduino Serial Monitor so it does not own
the ESP32 port. The desktop launcher starts missing services and opens the editor;
its logs are in `artifacts/editor.log` and `artifacts/usb.log`.

## Rebuild and verify

```bash
npm test
npm run build
../Kenny---Automotive-self-driving-trash-can/.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
```

The ARM64 TypeScript native package must be installed when building on this Pi.
If a lockfile created on another architecture omits it:

```bash
npm install --no-save --package-lock=false @typescript/typescript-linux-arm64@7.0.2
```

`tests/check_usb_browser.py` tests the real model/map pipeline with mocked USB.
Its `--live-zero` option verifies the full path through the connected ESP32 with
power fixed to zero, including completion and STOP, without commanding movement.
