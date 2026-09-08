import re
import threading
from pathlib import Path

import httpx

from py_st.services.dashboard import dashboard_server
from py_st.services.intelligence import Intelligence


def test_dashboard_shared_data_and_guarded_control(tmp_path: Path) -> None:
    # Arrange
    store = Intelligence(tmp_path / ".state/intelligence.sqlite3")
    store.observe("r:a", "agent", "a", {"credits": 175000})
    store.close()
    server = dashboard_server(tmp_path, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with httpx.Client(base_url=origin) as client:
            # Act
            page = client.get("/")
            match = re.search('nonce="([a-f0-9]+)"', page.text)
            assert match is not None
            csrf = match.group(1)
            data = client.get("/api/report").json()
            denied = client.post(
                "/api/control", json={"action": "pause", "csrf": csrf}
            )
            hostile = client.get("/api/report", headers={"Host": "evil.test"})
            paused = client.post(
                "/api/control",
                headers={"Origin": origin},
                json={"action": "pause", "csrf": csrf},
            )
            # Assert
            assert data["credits"][0]["credits"] == 175000
            assert denied.status_code == hostile.status_code == 403
            assert paused.json()["paused"]
            assert (tmp_path / "STOP").exists()
            assert (
                "frame-ancestors 'none'"
                in page.headers["Content-Security-Policy"]
            )
            assert client.get("/.env").status_code == 404
            resumed = client.post(
                "/api/control",
                headers={"Origin": origin},
                json={"action": "resume", "csrf": csrf},
            )
            assert not resumed.json()["paused"]
            assert not (tmp_path / "STOP").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
