from tests.dashboard.test_service import result

from brain.dashboard import create_app


def test_final_read_only_control_center_contract_is_complete():
    service = create_app(lambda: result())
    assert service.get("/health") == {"status": "ok", "read_only": True}
    for route in ("/market", "/snapshot", "/decision", "/risk", "/position", "/observability", "/data-quality", "/feed"):
        assert service.get(route)
    for route in ("/order", "/orders", "/trade", "/execute", "/cancel"):
        try:
            service.get(route)
        except PermissionError:
            pass
        else:
            raise AssertionError(f"mutation route was not rejected: {route}")
