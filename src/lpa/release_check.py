"""Check the actual Pages artifact in Chromium before uploading it."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from lpa.politikku_prerender import start_prerender_server


async def check_browser(output: Path) -> None:
    """Exercise published routes, their data and the Projection search."""
    from playwright.async_api import async_playwright

    projection = json.loads((output / "app/data/projection.json").read_text())
    sentiment = json.loads((output / "app/data/sentiment.json").read_text())
    lookup = json.loads((output / "data/lookup-index.json").read_text())
    if not lookup.get("postcodes") or not lookup.get("postcodeCatalogue"):
        raise ValueError("Lookup index is empty or malformed")
    postcode, seat_codes = next(
        (postcode, codes) for postcode, codes in lookup["postcodes"].items() if codes
    )
    server, port = start_prerender_server(output)
    origin = f"http://127.0.0.1:{port}"
    errors: list[str] = []
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            await page.route(
                lambda url: not url.startswith(origin + "/"),
                lambda route: route.abort(),
            )
            for prefix in ("", "ms/"):
                response = await page.goto(f"{origin}/{prefix}")
                if response is None or response.status != 200:
                    raise ValueError(f"Landing page failed: /{prefix}")
                await page.locator("[data-pk-lookup-input]").fill(postcode)
                await page.locator("[data-pk-lookup-form] button[type=submit]").click()
                await page.locator(
                    f'[data-pk-lookup-results] a[href="/app/#parlimen/parti/{seat_codes[0]}"]'
                ).wait_for(state="visible")
                for route in (
                    "dewan",
                    "bills",
                    "politicians",
                    "sentiment",
                    "projection",
                    "mp/P.107",
                ):
                    response = await page.goto(f"{origin}/{prefix}{route}/")
                    if response is None or response.status != 200:
                        raise ValueError(f"Published route failed: {prefix}{route}")
                    await page.wait_for_function(
                        "(route) => document.documentElement.dataset.renderComplete === route",
                        arg=route,
                    )
                    if route == "projection":
                        if await page.locator("#proj-rows [data-proj-seat]").count() != len(
                            projection["seats"]
                        ):
                            raise ValueError("Published Projection is missing Seat Calls")
                        if (
                            projection["computed_at"]
                            not in await page.locator("#projection-view").inner_text()
                        ):
                            raise ValueError("Published Projection has a stale date")
                        await page.locator("#proj-search").fill("NO_MATCH_RELEASE_CHECK")
                        if await page.locator("#proj-rows [data-proj-seat]").count() != 0:
                            raise ValueError("Projection search does not filter Seat Calls")
                    if route == "sentiment" and (
                        sentiment["computed_at"]
                        not in await page.locator("#sentiment-view").inner_text()
                    ):
                        raise ValueError("Published Sentiment has a stale date")
            await browser.close()
        if errors:
            raise ValueError("Browser errors: " + "; ".join(errors))
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("public"))
    args = parser.parse_args()
    asyncio.run(check_browser(args.output_dir))


if __name__ == "__main__":
    main()
