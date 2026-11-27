# M32 Simulation

A local-first browser dashboard for monitoring a Midas M32. It runs natively on macOS, Linux and Windows, and in a local VS Code Dev Container. Codespaces is for UI and simulator development; its forwarded web port is not a route to a physical console on your home LAN.

## Current implementation

- FastAPI browser dashboard, polling the local API once per second.
- 32-channel state model with name, input source, fader, mute and scribble-strip colour.
- Channel-to-output mute matrix covering input channels, Aux inputs and FX returns across Main L/R, Mono/Centre and all 16 mix buses. It distinguishes channel mute, channel and destination mute-group assignments, channel and destination DCA mute/fader effects, send switch-off, send fader at zero, and destination mute/fader at zero.
- Reads the console's DCA Mutes and Hard Mutes preferences, and accounts for pre/post-fader send tap points when evaluating channel and DCA faders. Unknown mute-system preferences and parameters not yet received from the console are shown as CHECK rather than guessed. OPEN means the routing controls permit a signal path; it does not claim audio is currently present. A second Bus/Main-to-Matrix 1–6 matrix traces the downstream Matrix sends and Matrix output mute paths. A separate Routing map tab inventories input patch banks, AES50/Card/Out/Playback patch selections, output assignments, FX rack source/type/parameter data, direct-routing user assignments, inserts, pan/stereo links, solo and talkback configuration. The Routing map also inventories output source/tap points, polarity, delay and P16 speaker metadata.
- OSC simulator on UDP 10023 with deterministic Sunday service, full-band, mute/DCA and patching/visibility scenarios. The browser exposes scenario selection, a live OSC traffic log and a searchable, categorized OSC protocol catalogue. The catalogue covers documented address families and command classes, and labels simulator coverage as implemented, partial or known-unsupported. Every decoded inbound and outbound message is recorded with peer, arguments, outcome and timestamp; unsupported GET/SET addresses, malformed packets and send errors are explicitly highlighted. Logs are held in memory (up to 3,000 events) and can be filtered or cleared. OSC bundles are decoded into individual messages.
- Hardware mode uses a read-only OSC client with a Diagnostics tab and `/api/diagnostics` endpoint. It records enquiry coverage, missing/stale parameters, malformed packets, invalid response shapes/types, unexpected OSC addresses/peers, DNS failures and UDP send errors. Recent events and counters are retained in memory for the current process. Missing responses are kept separate from protocol errors because firmware may not implement every queried address. It sends /xremote, parameter enquiries and read-only meter subscriptions but never sends parameter SET messages.
- Channels are hidden if the input source is OFF or the scribble-strip colour is OFF.
- Tests cover state updates, input-source decoding, channel visibility, Aux/FX return paths, Matrix sends, output mute-path calculations and routing snapshot decoding.

**M32-Edit compatibility is experimental and incomplete.** The simulator currently supports selected parameter GET/SET state, identity/status queries, selected X32node groups and subscriptions, but it is not a full console emulator. The simulator log is intended to capture M32-Edit's actual startup and scene-transfer traffic. Any address shown as `unhandled_get` or `unhandled_set` is a concrete compatibility gap to investigate; no claim is made that scene loading works until that traffic has been observed and implemented.

## Run locally

Requirements: Python 3.11+.

- macOS/Linux: run bash ./run.sh.
- Windows PowerShell: run ./run.ps1. If script execution is restricted, use powershell -ExecutionPolicy Bypass -File .\run.ps1.

Open http://localhost:8000. The first run creates a local virtual environment and installs dependencies. Stop with Ctrl+C. The application reads an optional .env file automatically.

By default the dashboard listens on this computer only. To open it from a phone, tablet or another computer on the same LAN, start it with `WEB_HOST=0.0.0.0 ./run.sh` (macOS/Linux) or set `$env:WEB_HOST="0.0.0.0"` before running `./run.ps1` (PowerShell). Then browse to `http://<computer-LAN-IP>:8000`. Keep this LAN exposure on a trusted network; the dashboard currently has no login. For a memorable address, create a local DNS record such as `m32-simulation.home.arpa` pointing to the computer running the app.

The default mode is simulator and starts with the Sunday service scenario. Use the **Simulator / OSC log** tab to select other scenarios and inspect all traffic. The simulator binds to 0.0.0.0:10023 on IPv4 so M32-Edit can discover it using its /xinfo broadcast scan. Select M32-Simulation in the scan results, or enter 127.0.0.1 manually on the same Mac. This exposes the unauthenticated simulator to the local network; use it only on a trusted LAN and allow the app through the macOS firewall if prompted. Set SIMULATOR_HOST=127.0.0.1 to disable network discovery and restrict access to this Mac. The reported identity is configurable with SIMULATOR_NAME, SIMULATOR_MODEL, SIMULATOR_FIRMWARE and SIMULATOR_SERVER_VERSION. Do not point M32-Edit at the physical console while testing the simulator.

## Use a physical M32

Copy .env.example to .env, set M32_MODE=hardware, and set M32_HOST to the console's IP address. Run the app on a Mac/Linux/Windows machine on the same LAN as the console. The monitor listens on OSC_LISTEN_PORT (default 10024) and sends read-only enquiries to the console's UDP port 10023.

The hardware transport is deliberately read-only. Set `M32_HOST` to the console IP address (or a local DNS name resolving to it); this is not a web URL. The dashboard URL belongs to the computer running the app. The UI shows fader position as a normalized percentage, not calibrated dB. Separate meter subscriptions expose input, mix, FX, output and monitor meter streams.

## Dev Container

1. Install Docker Desktop (Mac/Windows) or Docker Engine + Compose (Linux), VS Code and the Dev Containers extension.
2. Open the repository in VS Code and select **Reopen in Container**.
3. Open forwarded HTTP port 8000.

The local Compose configuration publishes the simulator's UDP 10023 only on the host loopback interface, so M32-Edit on the same computer can connect without exposing the simulator to the LAN. Hardware OSC port 10024 is published for local container testing. GitHub Codespaces port forwarding is not a substitute for LAN UDP access to a physical M32.

## Configuration

- M32_MODE: simulator (default) or hardware.
- M32_HOST: physical console IP.
- M32_PORT: console UDP port (10023).
- OSC_LISTEN_HOST / OSC_LISTEN_PORT: local OSC receive endpoint in hardware mode.
- SIMULATOR_HOST / SIMULATOR_PORT: simulator bind address and UDP port.

## Development checks

    python -m pip install -e ".[dev]"
    python -m compileall -q m32_monitor tests
    pytest

GitHub Actions runs compile and pytest on Ubuntu, macOS and Windows using Python 3.12, plus Docker Compose validation and an image build. Node.js is not required by the project.

## Next work

1. Verify hardware OSC responses on the actual M32 and validate source/color values against the console.
2. Capture M32-Edit startup traffic and extend simulator protocol compatibility from observed requests.
3. Validate routing enums, output assignments, FX/insert responses and meter blob decoding against the actual console firmware.
4. Validate the diagnostics and response schemas against actual M32 firmware, then refine reconnect/timeout handling and connection configuration.
