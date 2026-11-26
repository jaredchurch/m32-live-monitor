from m32_monitor.diagnostics import OscDiagnostics


def test_diagnostics_tracks_cycle_coverage_and_recent_valid_response():
    diag = OscDiagnostics("192.0.2.10")
    diag.begin_cycle(["/info", "/ch/01/mix/fader"])
    diag.received("/info")
    snapshot = diag.snapshot(online=True)
    assert snapshot["cycle_complete"] is False
    assert snapshot["missing"] == []
    diag.last_cycle_at = diag.cycle_started_at + 1
    snapshot = diag.snapshot(online=True)
    assert snapshot["cycle_complete"] is True
    assert snapshot["received_count"] == 1
    assert snapshot["missing"] == ["/ch/01/mix/fader"]


def test_diagnostics_retains_bounded_recent_events_and_counters():
    diag = OscDiagnostics("192.0.2.10")
    for number in range(105):
        diag.event("invalid_responses", "bad value", "/ch/01/mix/fader", number)
    snapshot = diag.snapshot()
    assert snapshot["counters"]["invalid_responses"] == 105
    assert len(snapshot["events"]) == 50
    assert snapshot["last_error"]["detail"] == 104
