"""FastAPI entry point for the M32 Live Monitor."""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from m32_monitor.config import get_settings

app = FastAPI(
    title="M32 Live Monitor",
    version="0.1.0",
    description="Local-first, read-only monitoring for a Midas M32.",
)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>M32 Live Monitor</title>
        <style>
          body { font: 16px system-ui, sans-serif; max-width: 760px;
                 margin: 4rem auto; padding: 0 1.25rem; color: #20242a; }
          .status { padding: 1rem; border: 1px solid #ccd2d9; border-radius: 8px; }
          code { background: #f1f3f5; padding: .15rem .35rem; border-radius: 4px; }
        </style>
      </head>
      <body>
        <h1>M32 Live Monitor</h1>
        <div class="status">
          <strong>Application running.</strong>
          <p>This is the infrastructure scaffold. Console monitoring is not connected yet.</p>
          <p>Runtime status: <a href="/api/status">/api/status</a></p>
          <p>Health check: <a href="/health">/health</a></p>
        </div>
      </body>
    </html>
    """


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, object]:
    settings = get_settings()
    return {
        "application": "M32 Live Monitor",
        "mode": settings.mode,
        "m32_host": settings.m32_host if settings.mode == "hardware" else None,
        "m32_port": settings.m32_port,
        "osc_listen_port": settings.osc_listen_port,
        "connection": "not_implemented",
        "read_only": True,
    }
