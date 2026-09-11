"""Explicit local browser smoke test against the real shared datastore."""

import argparse
import fcntl
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from playwright.sync_api import Page


def check_read_only(page: "Page", origin: str) -> None:
    """Compare rendered values with the local server's stored report."""
    from playwright.sync_api import expect

    with page.expect_response("**/api/report?scope=*") as pending:
        page.goto(origin)
    response = pending.value
    assert response.ok, "Stored report unavailable"
    report = response.json()
    scopes = report.get("scopes", [])
    expect(page.locator("#scope option")).to_have_count(len(scopes))
    for scope in scopes or [None]:
        if scope is not None:
            with page.expect_response("**/api/report?scope=*") as pending:
                page.locator("#scope").select_option(scope)
            response = pending.value
            assert response.ok, f"Stored report unavailable for {scope}"
            report = response.json()
            assert report["scope"] == scope
        expect(page.locator("#state")).to_have_text(
            "STOP REQUESTED" if report["paused"] else "STOP CLEAR"
        )
        credits = report.get("credits", [])
        expected = format(credits[-1]["credits"], ",") if credits else "--"
        expect(page.locator("#credits")).to_have_text(expected)
        ships = report.get("ships", [])
        expect(page.locator("#fleet .ship")).to_have_count(len(ships))
        for index, ship in enumerate(ships):
            card = page.locator("#fleet .ship").nth(index)
            expect(card.locator("strong")).to_have_text(ship["data"]["symbol"])
            expect(card).to_contain_text(ship["data"]["nav"]["waypointSymbol"])
        prices = report.get("prices", [])
        expect(page.locator("#market-select option")).to_have_count(
            len(prices) + 1
        )
        if prices:
            page.locator('nav a[href="#markets"]').click()
            market = prices[0]
            page.locator("#market-select").select_option(market["key"])
            expect(page.locator("#market-asof")).to_contain_text(
                market["observed_at"]
            )
            goods = sorted(
                {
                    good["symbol"]
                    for good in market["data"].get("tradeGoods", [])
                    if isinstance(good, dict)
                    and isinstance(good.get("symbol"), str)
                }
            )
            expect(page.locator("#market-prices tr")).to_have_count(len(goods))
            if goods:
                with page.expect_response(
                    "**/api/market-history?*"
                ) as pending:
                    page.locator("#good-select").select_option(goods[0])
                assert pending.value.ok, "Stored market history unavailable"
                expect(page.locator("#market-status")).to_contain_text(
                    f"{goods[0]} / {market['key']}:"
                )
        expect(page.locator("#error")).to_have_text("")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= innerWidth"
        ), f"Horizontal overflow in scope {scope}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Preserve STOP and block browser writes; no control/model clicks",
    )
    parser.add_argument(
        "--root", type=Path, default=None, help="Ledger root (default: cwd)"
    )
    args = parser.parse_args(argv)
    root = (args.root or Path.cwd()).resolve()
    if not args.read_only and (root / "STOP").exists():
        raise RuntimeError(
            "Preserve existing STOP; do not run control smoke test"
        )
    if args.read_only and not (root / ".state/intelligence.sqlite3").is_file():
        raise RuntimeError(
            f"Existing ledger required: {root / '.state/intelligence.sqlite3'}"
        )

    from playwright.sync_api import Route, expect, sync_playwright

    from py_st.services.dashboard import dashboard_server

    with (root / ".state/automation.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Automation active; do not run dashboard smoke tests"
            ) from None
        stop_before = (root / "STOP").exists()
        try:
            server = dashboard_server(root, 0)
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            errors: list[str] = []
            blocked: list[str] = []
            origin = f"http://127.0.0.1:{server.server_port}"

            def read_only_route(route: Route) -> None:
                request = route.request
                if request.method != "GET" or not request.url.startswith(
                    origin + "/"
                ):
                    blocked.append(f"{request.method} {request.url}")
                    route.abort()
                else:
                    route.continue_()

            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(
                        channel="chrome", headless=True
                    )
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1080},
                        locale="en-US",
                        service_workers="block",
                    )
                    if args.read_only:
                        context.route("**/*", read_only_route)
                    page = context.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    if args.read_only:
                        run_id = uuid4().hex
                        for name, width, height in (
                            ("desktop", 1440, 1080),
                            ("mobile", 390, 844),
                        ):
                            page.set_viewport_size(
                                {"width": width, "height": height}
                            )
                            check_read_only(page, origin)
                            path = root / (
                                ".state/dashboard-product-readonly-"
                                f"{run_id}-{name}.png"
                            )
                            page.screenshot(path=str(path), full_page=True)
                            print(f"Screenshot: {path}")
                        assert not blocked, blocked
                    else:
                        page.goto(origin)
                        expect(page.locator("#credits")).not_to_have_text("--")
                        page.get_by_role(
                            "button", name="Pause automation", exact=True
                        ).click()
                        expect(page.locator("#state")).to_have_text(
                            "STOP REQUESTED"
                        )
                        assert (root / "STOP").exists()
                        page.get_by_role(
                            "button", name="Clear stop", exact=True
                        ).click()
                        expect(page.locator("#state")).to_have_text(
                            "STOP CLEAR"
                        )
                        assert not (root / "STOP").exists()
                        page.screenshot(
                            path=str(root / ".state/dashboard-desktop.png"),
                            full_page=True,
                        )
                        page.set_viewport_size({"width": 390, "height": 844})
                        page.screenshot(
                            path=str(root / ".state/dashboard-mobile.png"),
                            full_page=True,
                        )
                        assert page.evaluate(
                            "document.documentElement.scrollWidth "
                            "<= innerWidth"
                        )
                    assert not errors, errors
                    browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join()
        finally:
            if args.read_only and (root / "STOP").exists() != stop_before:
                raise RuntimeError(
                    "STOP existence changed during read-only smoke; "
                    "left untouched (no restoration attempted)"
                )
    if args.read_only:
        print(
            "Desktop/mobile, stored credits/fleet and available Market Desk: "
            "passed; no browser writes, STOP existence unchanged"
        )
    else:
        print("Desktop/mobile render, real credits, pause/resume: passed")


if __name__ == "__main__":
    main()
