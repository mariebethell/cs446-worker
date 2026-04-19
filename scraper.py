from playwright.sync_api import sync_playwright
import time

def get_wunderground_forecast(zipcode: str):
    """
    Get 10-day forecast from WunderGround.
    """
    start = time.time()

    url = f"https://www.wunderground.com/forecast/us/ca/{zipcode}"
    print(url)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=15000)

        page.wait_for_selector(".temp-hi", timeout=10000)

        highs = page.locator(".temp-hi").all_text_contents()
        lows = page.locator(".temp-lo").all_text_contents()
        days = page.locator(".forecast-date .obs-date div").all_text_contents()

        for d, h, l in zip(days, highs, lows):
            print(d, h, l)

        browser.close()
    
    print("Time taken:", time.time() - start)