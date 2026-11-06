"""
Drive a throwaway Home Assistant through the share and receive flows and save the README screenshots.

Called by script/screenshots, which starts Home Assistant and the telemetry server first. Needs playwright and httpx.
"""

import argparse
from pathlib import Path
import secrets
import sys
import time

import httpx
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

USERNAME = "demo"
PASSWORD = secrets.token_urlsafe(16)
SHARE_TOKEN = "demo-write-token"
READ_TOKEN = "demo-read-token"
SHARED = ["Outdoor temperature", "Outdoor humidity", "Solar power", "Water tank level", "Barn door"]
VIEWPORT = {"width": 1280, "height": 860}


def wait_for(url: str, timeout: float = 300) -> None:
    """Wait until url answers, or exit."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=5).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    sys.exit(f"{url} did not answer within {timeout:.0f} seconds")


def onboard(ha: str) -> None:
    """Create the demo user and finish onboarding through the API."""
    client_id = f"{ha}/"
    with httpx.Client(base_url=ha, timeout=30) as client:
        response = client.post(
            "/api/onboarding/users",
            json={"client_id": client_id, "name": "Demo", "username": USERNAME, "password": PASSWORD, "language": "en"},
        )
        response.raise_for_status()
        token = client.post(
            "/auth/token",
            data={"grant_type": "authorization_code", "code": response.json()["auth_code"], "client_id": client_id},
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/onboarding/core_config", headers=headers).raise_for_status()
        client.post("/api/onboarding/analytics", headers=headers).raise_for_status()
        client.post(
            "/api/onboarding/integration",
            headers=headers,
            json={"client_id": client_id, "redirect_uri": f"{client_id}?auth_callback=1"},
        ).raise_for_status()


class Shooter:
    """Walk the UI and save one PNG per step."""

    def __init__(self, page: Page, ha: str, server_url: str, out: Path) -> None:
        """Remember where to go and where to write."""
        self.page = page
        self.ha = ha
        self.server_url = server_url
        self.out = out

    def shot(self, name: str, wait: int = 1500) -> None:
        """Let the UI settle, then save the viewport as out/name.png."""
        self.page.wait_for_timeout(wait)
        self.page.screenshot(path=self.out / f"{name}.png")

    def login(self) -> None:
        """Log in through the login form."""
        page = self.page
        page.goto(f"{self.ha}/")
        page.get_by_label("Username").fill(USERNAME)
        page.get_by_label("Password", exact=True).fill(PASSWORD)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_url(lambda url: "auth_callback" not in url and url.rstrip("/") != self.ha, timeout=60000)
        page.wait_for_timeout(1500)

    def confirm_http_settings(self) -> None:
        """Accept the port change Home Assistant asks about once, because the throwaway instance runs on its own port."""
        dialog = self.page.locator("dialog-http-pending-config")
        try:
            dialog.get_by_role("button", name="Confirm").click(timeout=5000)
        except PlaywrightTimeoutError:
            return
        self.page.wait_for_timeout(1000)

    def pick_entity(self, name: str, *, first: bool) -> None:
        """Add one entity in an entity picker."""
        page = self.page
        page.get_by_text("Select an entity" if first else "Add entity").last.click()
        page.wait_for_timeout(800)
        page.keyboard.type(name)
        page.wait_for_timeout(1200)
        page.get_by_text(name, exact=True).last.click()
        page.wait_for_timeout(800)

    def start_flow(self, mode: str, token: str, prefix: str, *, capture_start: bool) -> None:
        """Open Add integration, choose the mode and fill in the connection step."""
        page = self.page
        page.goto(f"{self.ha}/config/integrations/dashboard")
        page.wait_for_timeout(2000)
        self.confirm_http_settings()
        page.get_by_role("button", name="Add integration").click()
        page.wait_for_timeout(1500)
        page.keyboard.type("Hofm")
        page.wait_for_timeout(1500)
        if capture_start:
            self.shot("setup-search", 0)
        page.get_by_text("Hofmätteli Telemetry").last.click()
        page.wait_for_timeout(2500)
        if capture_start:
            self.shot("setup-choose-mode", 0)
        page.get_by_text(mode).click()
        page.wait_for_timeout(1500)
        page.locator("input[name=url]").fill(self.server_url)
        page.locator("input[name=api_token]").fill(token)
        self.shot(f"{prefix}-connect", 500)
        page.get_by_role("button", name="Submit").click()
        page.wait_for_timeout(2500)

    def share(self) -> None:
        """Set up sharing for the demo entities."""
        page = self.page
        self.start_flow("Share entities from this Home Assistant", SHARE_TOKEN, "share", capture_start=True)
        for index, name in enumerate(SHARED):
            self.pick_entity(name, first=index == 0)
        self.shot("share-entities", 300)
        page.get_by_role("button", name="Submit").click()
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="Finish").click()
        page.wait_for_timeout(1500)

    def receive(self) -> None:
        """Set up receiving for everything the share entry pushed."""
        page = self.page
        self.start_flow("Receive entities someone shares", READ_TOKEN, "receive", capture_start=False)
        for name in sorted(SHARED):
            page.get_by_text(f"{name} (").first.click()
        self.shot("receive-entities", 300)
        page.get_by_role("button", name="Submit").click()
        self.shot("receive-device", 3000)
        page.get_by_role("button", name="Skip and finish").click()
        page.wait_for_timeout(1500)

    def results(self) -> None:
        """Capture the integration page, the device, an entity's details and the Configure dialog."""
        page = self.page
        integration_page = f"{self.ha}/config/integrations/integration/hofmaetteli_telemetry"
        page.goto(integration_page)
        self.shot("result-entries", 3000)

        page.get_by_text("Telemetry server •").click()
        self.shot("result-device", 3000)
        page.get_by_text("Outdoor temperature").first.click()
        page.wait_for_timeout(2000)
        page.locator("ha-more-info-dialog ha-button-menu, ha-more-info-dialog ha-dropdown").last.click()
        page.wait_for_timeout(1000)
        page.get_by_text("Details", exact=True).last.click()
        self.shot("result-entity-details", 2000)
        page.keyboard.press("Escape")

        page.goto(integration_page)
        page.wait_for_timeout(2500)
        page.get_by_role("button", name="Configure").last.click()
        page.get_by_text("Choose entities to share").wait_for(timeout=10000)
        self.shot("configure", 1500)


def main() -> int:
    """Run every step; on failure keep a debug screenshot next to the logs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--ha", required=True)
    parser.add_argument("--server-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    wait_for(f"{args.server_url}/docs")
    wait_for(f"{args.ha}/api/onboarding")
    onboard(args.ha)

    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport=VIEWPORT, locale="en-US", color_scheme="light")
        page = context.new_page()
        shooter = Shooter(page, args.ha, args.server_url, args.out)
        try:
            shooter.login()
            shooter.share()
            shooter.receive()
            shooter.results()
        except Exception:
            page.screenshot(path=".local/screenshots/debug.png")
            raise
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
