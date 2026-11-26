from m32_monitor.routing import INPUT_BANKS, OUTPUT_BANKS, RoutingState


def test_input_patch_enum_decodes_documented_bank():
    state = RoutingState()
    state.update("/config/routing/IN/1-8", 4)
    item = next(x for section in state.snapshot()["sections"] for x in section["items"]
                if x["address"] == "/config/routing/IN/1-8")
    assert item["known"] is True
    assert item["display"] == INPUT_BANKS[4]


def test_unknown_patch_value_is_not_guessed():
    state = RoutingState()
    state.update("/config/routing/IN/1-8", 99)
    item = next(x for section in state.snapshot()["sections"] for x in section["items"]
                if x["address"] == "/config/routing/IN/1-8")
    assert item["display"] == "Unknown enum (99)"


def test_output_patch_and_fx_assignments_are_exposed():
    state = RoutingState()
    state.update("/config/routing/AES50A/1-8", 0)
    state.update("/outputs/main/01", 7)
    state.update("/fx/1/type", 3)
    state.update("/fx/1/source", 41)
    snapshot = state.snapshot()
    assert any(x["address"] == "/config/routing/AES50A/1-8" and x["known"]
               for section in snapshot["sections"] for x in section["items"])
    assert next(x for x in snapshot["outputs"] if x["address"] == "/outputs/main/01")["value"] == 7
    assert any(x["address"] == "/fx/1/type" and x["value"] == 3 for x in snapshot["effects"])


def test_solo_talkback_direct_routing_and_insert_values_are_retained():
    state = RoutingState()
    for address, value in (
        ("/config/solo/source", 2),
        ("/config/talk/enable", 1),
        ("/config/userrout/out/01", 45),
        ("/ch/01/insert", 1),
    ):
        assert state.update(address, value)
    addresses = {x["address"] for x in state.snapshot()["special"]}
    assert {"/config/solo/source", "/config/talk/enable",
            "/config/userrout/out/01", "/ch/01/insert"} <= addresses
