# M32 Live Monitor

A local-first browser dashboard for monitoring a Midas M32. The application is designed to
run natively on macOS and Linux, with a Dev Container for consistent development in VS Code
and GitHub Codespaces.

> **Current state:** infrastructure scaffold only. The web server and health/status endpoints
> run, but M32 OSC communication, live channel data, and the M32-Edit-compatible simulator
> have not been implemented yet. The application is read-only by design at this stage.

## Quick start on macOS or Linux

Requirements: Python 3.11 or newer.

From a terminal in the repository:

```bash
bash ./run.sh
```

Then open http://localhost:8000.

The first run creates a local virtual environment and installs the Python dependencies.
Subsequent runs reuse it. Stop the server with Ctrl+C.

## Start in a Dev Container

1. Install Docker Desktop (macOS) or Docker Engine and the Docker Compose plugin (Linux).
2. Install Visual Studio Code and its Dev Containers extension.
3. Open this repository in VS Code.
4. Choose **Reopen in Container** from the command palette.
5. Open the forwarded port 8000 when the container starts.

The same Dev Container definition is used by GitHub Codespaces. Create a Codespace from
this repository and wait for the container to build; port 8000 hosts the browser interface.

The container publishes UDP port 10024 in preparation for the OSC receive service. That
does not make a physical M32 reachable from Codespaces: Codespaces is for the UI, code and
simulator work. For a real console connection, run the backend natively on a Mac/Linux
machine on the same network as the M32. A locally running container may also be able to
reach the console, subject to the host network and firewall configuration.

## Configuration

Copy .env.example to .env and adjust the values when the OSC transport is implemented:

- M32_MODE: simulator or hardware (defaults to simulator).
- M32_HOST: IP address of the physical M32.
- M32_PORT: M32 OSC port (default 10023).
- OSC_LISTEN_PORT: local OSC receive port reserved by this scaffold (default 10024).

The current scaffold reports the selected mode but does not yet open an OSC connection.

## Development

Install the development dependencies and run the checks:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
```

GitHub Actions runs lint and tests on pushes and pull requests. The workflow uses Python 3.12
and does not require Node.js.

## Planned next steps

1. Implement and test the OSC transport in read-only mode against a real M32.
2. Add a deterministic virtual console for dashboard testing.
3. Expand simulator protocol coverage and validate M32-Edit compatibility separately.
4. Build the live channel, mute, input mapping and scribble-strip dashboard.
5. Add native packaging only if launching through the local browser becomes inconvenient.

Simulator traffic and hardware traffic will remain explicitly separated so test messages
cannot accidentally control a live mixing console.
