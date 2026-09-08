"""Explicit local browser smoke test against the real shared datastore."""

import fcntl
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright

from py_st.services.dashboard import dashboard_server


def main() -> None:
    root = Path.cwd()
    if (root / "STOP").exists():
        raise RuntimeError(
            "Preserve existing STOP; do not run control smoke test"
        )
    lock = (root / ".state/automation.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError(
            "Automation active; do not toggle STOP in tests"
        ) from None
    server = dashboard_server(root, 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome", headless=True
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1080})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#credits")).not_to_have_text("--")
            page.get_by_role(
                "button", name="Pause automation", exact=True
            ).click()
            expect(page.locator("#state")).to_have_text("STOP REQUESTED")
            assert (root / "STOP").exists()
            page.get_by_role("button", name="Clear stop", exact=True).click()
            expect(page.locator("#state")).to_have_text("STOP CLEAR")
            assert not (root / "STOP").exists()
            page.screenshot(
                path=str(root / ".state/dashboard-desktop.png"), full_page=True
            )
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(
                path=str(root / ".state/dashboard-mobile.png"), full_page=True
            )
            assert page.evaluate(
                "document.documentElement.scrollWidth <= innerWidth"
            )
            assert not errors, errors
            print("Desktop/mobile render, real credits, pause/resume: passed")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        lock.close()


if __name__ == "__main__":
    main()
