# M32 Live Monitor

A local-first browser dashboard for monitoring a Midas M32. It runs natively on macOS, Linux and Windows, and in a local VS Code Dev Container. Codespaces is for UI and simulator development; its forwarded web port is not a route to a physical console on your home LAN.

## Current implementation

- FastAPI browser dashboard, polling the local API once per second.
- 32-channel state model with name, input source, fader, mute and scribble-strip colour.
- OSC simulator on UDP 10023. It supports basic parameter GET/SET, /info, /xinfo, /status and /xremote for the subset represented in the dashboard.
- Hardware mode uses a read-only OSC client. It sends /xremote and parameter enquiries but never sends parameter SET messages.
- Channels are hidden if the input source is OFF or the scribble-strip colour is OFF.
- Tests cover state updates, input-source decoding and channel visibility.

**M32-Edit compatibility is experimental and incomplete.** The simulator is not a full console emulator. It is an early protocol subset intended to establish the transport and state model; further protocol capture and iterative compatibility testing will be required before relying on it with M32-Edit.

## Run locally

Requirements: Python 3.11+.

- macOS/Linux: run bash ./run.sh.
- Windows PowerShell: run ./run.ps1. If script execution is restricted, use powershell -ExecutionPolicy Bypass -File .\run.ps1.

Open http://localhost:8000. The first run creates a local virtual environment and installs dependencies. Stop with Ctrl+C. The application reads an optional .env file automatically.

The default mode is simulator. The app binds UDP 10023 for the virtual console. In M32-Edit, create a connection to the computer's LAN IP address and port 10023. Do not point M32-Edit at the physical console while testing the simulator. If UDP 10023 is already in use, stop the other service or change SIMULATOR_PORT.

## Use a physical M32

Copy .env.example to .env, set M32_MODE=hardware, and set M32_HOST to the console's IP address. Run the app on a Mac/Linux/Windows machine on the same LAN as the console. The monitor listens on OSC_LISTEN_PORT (default 10024) and sends read-only enquiries to the console's UDP port 10023.

The hardware transport is deliberately read-only. The UI currently shows fader position as a normalized percentage, not calibrated dB. It does not yet display audio meter levels.

## Dev Container

1. Install Docker Desktop (Mac/Windows) or Docker Engine + Compose (Linux), VS Code and the Dev Containers extension.
2. Open the repository in VS Code and select **Reopen in Container**.
3. Open forwarded HTTP port 8000.

The local Compose configuration publishes UDP 10023 for M32-Edit to reach the simulator through the host. This UDP mapping is useful for a local container; GitHub Codespaces port forwarding is not a substitute for LAN UDP access to a physical M32.

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

GitHub Actions runs compile and pytest on Ubuntu, macOS and Windows using Python 3.12. Node.js is not required by the project.

## Next work

1. Verify hardware OSC responses on the actual M32 and validate source/color values against the console.
2. Capture M32-Edit startup traffic and extend simulator protocol compatibility from observed requests.
3. Add audio meter data and a more useful channel-strip layout.
4. Add reconnect/timeout handling and a small connection configuration page.
