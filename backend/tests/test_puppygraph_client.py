from app.core.config import Settings
from app.services.puppygraph_client import PuppyGraphClient, load_puppygraph_schema_stub


def test_schema_stub_loads_vertices_and_edges() -> None:
    stub = load_puppygraph_schema_stub()
    assert stub.get("version")
    assert len(stub.get("vertices") or []) >= 3
    assert len(stub.get("edges") or []) >= 1


def test_client_disabled_by_default() -> None:
    client = PuppyGraphClient(Settings(_env_file=None, puppygraph_enabled=False))
    assert not client.configured
    summary = client.schema_summary()
    assert summary["enabled"] is False
    assert "SalesOffice" in summary.get("vertex_labels", [])
