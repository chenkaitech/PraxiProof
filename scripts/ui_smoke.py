"""Walk through the running web app in a real browser, fail on any console/network/rendering problem, and
save screenshots into the repository (docs/screenshots by default).

Needs Playwright and a Chrome install:  pip install playwright   (uses the system Chrome, no browser download)
Usage:  python scripts/ui_smoke.py --base http://192.168.71.111:8090 [--out docs/screenshots] [--skip-agent]
If a system proxy is set, bypass it for the app host:  NO_PROXY=<host> python scripts/ui_smoke.py ...
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWS = ["dashboard", "manuals", "videos", "runs", "skills", "reports", "evaluation", "settings"]
AGENT_WAIT_MS = 300_000


def pick_run(base: str) -> str:
    runs = json.loads(urllib.request.urlopen(f"{base}/api/runs", timeout=30).read())
    with_violation = [r for r in runs if r.get("status") == "done" and r.get("violations", 0) > 0]
    if not with_violation:
        sys.exit("no finished run with a violation to open; create one first")
    return with_violation[0]["id"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "screenshots")
    ap.add_argument("--run", help="run id to open (default: latest finished run that has a violation)")
    ap.add_argument("--skip-agent", action="store_true", help="skip the steps that call the LLM")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    run_id = args.run or pick_run(args.base)
    problems: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
        page.on("pageerror", lambda e: problems.append(f"pageerror: {str(e)[:150]}"))
        page.on("console", lambda m: problems.append(f"console error: {m.text[:150]}") if m.type == "error" else None)
        page.on("response", lambda r: problems.append(f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)

        def check_text(label: str) -> None:
            text = page.inner_text("#view")
            for bad in ("undefined", "NaN", "[object", "eval.", "rca.", "trace."):
                if bad in text:
                    problems.append(f"{label}: page text contains {bad!r}")

        for view in VIEWS:
            page.goto(f"{args.base}/#{view}")
            if view == "settings":
                page.wait_for_selector("#settings-form", timeout=20_000)
            elif view == "evaluation":
                page.wait_for_selector(".agent-flow", timeout=20_000)
            else:
                page.wait_for_timeout(1500)
            check_text(view)
            if view in ("dashboard", "runs", "evaluation"):
                page.screenshot(path=str(args.out / f"{view}.png"), full_page=(view == "evaluation"))
            print(f"ok  {view}")

        page.goto(f"{args.base}/#evaluation")
        page.wait_for_selector(".agent-flow", timeout=20_000)
        page.click("#lang-toggle")
        page.wait_for_selector(".agent-flow", timeout=20_000)
        page.wait_for_timeout(600)
        check_text("evaluation (zh)")
        if "评测" not in page.inner_text("#view h1"):
            problems.append("language toggle did not switch the Evaluation page to Chinese")
        page.screenshot(path=str(args.out / "evaluation-zh.png"), full_page=True)
        page.click("#lang-toggle")
        page.wait_for_timeout(600)

        # Regression: Settings waits on a slow request; leaving it early must not let it overwrite the next page.
        page.goto(f"{args.base}/#settings")
        page.evaluate(f"location.hash = '#run/{run_id}'")
        page.wait_for_selector("#question", timeout=20_000)
        page.wait_for_timeout(3000)
        if page.locator("#settings-form").count() or not page.locator("#question").count():
            problems.append("a slow Settings render overwrote the page the user had already navigated to")
        check_text(f"run {run_id}")
        print(f"ok  run {run_id} (and no stale render overwrote it)")

        if not args.skip_agent:
            page.click("[data-why]")
            page.wait_for_selector(".why-slot .rca-card", timeout=AGENT_WAIT_MS)
            page.locator(".verdict", has=page.locator("[data-why]")).first.screenshot(path=str(args.out / "run-why.png"))
            print("ok  per-rule root-cause analysis")

            page.fill("#question", "Why did the timing rule fail? Explain the root cause.")
            page.click("#ask")
            page.wait_for_selector("#answer .trace", timeout=AGENT_WAIT_MS)
            agents = page.locator("#answer .agent-chip").all_inner_texts()
            if len(agents) < 2:
                problems.append(f"agent trace shows {agents}, expected the Compliance and RCA agents")
            page.locator("#answer").screenshot(path=str(args.out / "run-agent-trace.png"))
            print(f"ok  agent trace {agents}")
        browser.close()

    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print(f"\nall checks passed; screenshots in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
