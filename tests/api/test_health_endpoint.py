from fastapi.testclient import TestClient


def test_healthz_reports_ok(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "surge"
    assert body["version"]


def test_unknown_route_is_404(client: TestClient) -> None:
    assert client.get("/does-not-exist").status_code == 404
