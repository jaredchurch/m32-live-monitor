# M32 Live Monitor

A local-first browser dashboard for monitoring a Midas M32. It runs natively on macOS, Linux and Windows, and in a local VS Code Dev Container. Codespaces is for UI and simulator development; its forwarded web port is not a route to a physical console on your home LAN.

## Current implementation

- FastAPI browser dashboard, polling the local API once per second.
- 32-channel state model with name, input source, fader, mute and scribble-strip colour.
- Channel-to-output mute matrix covering input channels, Aux inputs and FX returns across Main L/R, Mono/Centre and all 16 mix buses. It distinguishes channel mute, channel and destination mute-group assignments, channel and destination DCA mute/fader effects, send switch-off, send fader at zero, and destination mute/fader at zero.
- Reads the console's DCA Mutes and Hard Mutes preferences, and accounts for pre/post-fader send tap points when evaluating channel and DCA faders. Unknown mute-system preferences and parameters not yet received from the console are shown as CHECK rather than guessed. OPEN means the routing controls permit a signal path; it does not claim audio is currently present. A second Bus/Main-to-Matrix 1–6 matrix traces the downstream Matrix sends and Matrix output mute paths. A separate Routing map tab inventories input patch banks, AES50/Card/Out/Playback patch selections, output assignments, FX rack source/type, direct-routing user assignments, inserts, solo and talkback configuration.
- OSC simulator on UDP 10023. It supports basic parameter GET/SET, /info, /xinfo, /status and /xremote for the subset represented in the dashboard.
- Hardware mode uses a read-only OSC client. It sends /xremote, parameter enquiries and read-only meter subscriptions but never sends parameter SET messages.
- Channels are hidden if the input source is OFF or the scribble-strip colour is OFF.
- Tests cover state updates, input-source decoding, channel visibility, Aux/FX return paths, Matrix sends, output mute-path calculations and routing snapshot decoding.

**M32-Edit compatibility is experimental and incomplete.** The simulator is not a full console emulator. It is an early protocol subset intended to establish the transport and state model; further protocol capture and iterative compatibility testing will be required before relying on it with M32-Edit.

## Run locally

Requirements: Python 3.11+.

- macOS/Linux: run bash ./run.sh.
- Windows PowerShell: run ./run.ps1. If script execution is restricted, use powershell -ExecutionPolicy Bypass -File .\run.ps1.

Open http://localhost:8000. The first run creates a local virtual environment and installs dependencies. Stop with Ctrl+C. The application reads an optional .env file automatically.

The default mode is simulator. The native simulator binds to 127.0.0.1:10023 (loopback only). In M32-Edit on the same computer, connect to 127.0.0.1 on UDP port 10023. If M32-Edit runs on another computer, change SIMULATOR_HOST to 0.0.0.0 and connect to the host computer's LAN IP. Do not point M32-Edit at the physical console while testing the simulator.

## Use a physical M32

Copy .env.example to .env, set M32_MODE=hardware, and set M32_HOST to the console's IP address. Run the app on a Mac/Linux/Windows machine on the same LAN as the console. The monitor listens on OSC_LISTEN_PORT (default 10024) and sends read-only enquiries to the console's UDP port 10023.

The hardware transport is deliberately read-only. The UI currently shows fader position as a normalized percentage, not calibrated dB. It does not yet display audio meter levels.

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
3. Validate every routing enum and output assignment against the actual console firmware; extend source labels and FX/insert decoding where the console returns structured values.
4. Add audio meter data, confirm monitor/talkback paths, and improve reconnect/timeout handling and connection configuration.
