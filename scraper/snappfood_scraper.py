#!/usr/bin/env python3
"""
Snappfood vendor menu scraper -> CSV (category,name,description,price,image)

Setup:
    pip install playwright
    # No `playwright install` needed if Chrome/Chromium/Brave/Edge is already installed;
    # it is auto-detected, or pass --browser-path /path/to/browser

Usage:
    python snappfood_scraper.py "https://snappfood.ir/restaurant/menu/<vendor-slug>/" -o menu.csv
    python snappfood_scraper.py <url> --full-size-images --headed

Notes:
  * The menu list is virtualized, so items are collected while scrolling.
  * Price = the regular price (data-product-fee), NOT the discounted price.
    Values are in Toman, exactly as shown on the site.
"""
import argparse
import csv
import re
import shutil
import sys
import time

from playwright.sync_api import sync_playwright

EXTRACT_JS = """
() => {
  const out = [];
  document.querySelectorAll('[data-testid^="ProductCard-"]').forEach(card => {
    const id = card.getAttribute('data-product-id') || card.getAttribute('data-testid');
    const name = card.getAttribute('data-product-name') ||
                 (card.querySelector('h3') || {}).textContent || '';
    const category = card.getAttribute('data-category-name') || '';

    // description: <p> in the sibling block right after the <h3> wrapper
    let desc = '';
    const h3 = card.querySelector('h3');
    if (h3 && h3.parentElement && h3.parentElement.nextElementSibling) {
      const p = h3.parentElement.nextElementSibling.querySelector('p');
      if (p) desc = p.textContent;
    }

    // regular (non-discounted) price lives on the inner element with data-product-fee
    const priceEl = card.querySelector('[data-product-fee]');
    let price = priceEl ? priceEl.getAttribute('data-product-fee') : '';
    if (!price && priceEl) price = priceEl.getAttribute('data-product-price') || '';
    if (!price) {
      const t = card.querySelector('.price span[dir="ltr"]');
      price = t ? t.textContent : '';
    }

    const img = card.querySelector('img');
    const image = img ? (img.getAttribute('src') || '') : '';

    out.push({id, category, name, desc, price, image});
  });
  return out;
}
"""


def clean_text(s: str) -> str:
    return re.sub(r"[ \t]*\n[ \t]*", " ", (s or "")).strip()


def clean_price(s: str) -> str:
    # strip separators (٬ , space) and convert Persian/Arabic digits to ASCII
    trans = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    digits = re.sub(r"\D", "", (s or "").translate(trans))
    return digits


def full_size(url: str) -> str:
    # https://cdn.snappfood.ir/200x201/cdn/... -> https://cdn.snappfood.ir/cdn/...
    return re.sub(r"(cdn\.snappfood\.ir)/\d+x\d+/", r"\1/", url)


def find_system_browser():
    """Find an installed Chromium-based browser so no Playwright download is needed."""
    names = [
        "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
        "brave-browser", "brave", "microsoft-edge", "microsoft-edge-stable",
        "vivaldi", "opera",
    ]
    for n in names:
        path = shutil.which(n)
        if path:
            return path
    return None


def scrape(url: str, headed: bool, step: int, pause: float, full_imgs: bool,
           browser_path: str = None):
    items = {}  # id -> row, insertion ordered (keeps menu order)
    with sync_playwright() as p:
        exe = browser_path or find_system_browser()
        if exe:
            print(f"Using browser: {exe}")
            browser = p.chromium.launch(executable_path=exe, headless=not headed)
        else:
            # falls back to Playwright's own bundled Chromium (needs `playwright install chromium`)
            browser = p.chromium.launch(headless=not headed)
        ctx = browser.new_context(locale="fa-IR", viewport={"width": 430, "height": 900})
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector('[data-testid^="ProductCard-"]', timeout=60000)

        def harvest():
            added = 0
            for r in page.evaluate(EXTRACT_JS):
                if r["id"] in items:
                    continue
                img = r["image"]
                if full_imgs and img:
                    img = full_size(img)
                items[r["id"]] = {
                    "category": clean_text(r["category"]),
                    "name": clean_text(r["name"]),
                    "description": clean_text(r["desc"]),
                    "price": clean_price(r["price"]),
                    "image": img,
                }
                added += 1
            return added

        page.mouse.move(200, 500)

        # Pass 1: scroll down; stop only after many rounds with nothing new
        idle_rounds = 0
        while idle_rounds < 15:
            added = harvest()
            idle_rounds = 0 if added else idle_rounds + 1
            # bring the last rendered card to the bottom of the viewport, then wheel-scroll
            page.evaluate(
                """() => {
                  const c = document.querySelectorAll('[data-testid^="ProductCard-"]');
                  if (c.length) c[c.length - 1].scrollIntoView({block: 'end'});
                }"""
            )
            page.mouse.wheel(0, step)
            time.sleep(pause)

        # Pass 2: click every category tab so each section gets rendered and harvested
        tabs = page.evaluate(
            """() => [...document.querySelectorAll('.byn-tab-item[data-category-id]')]
                      .map(t => t.getAttribute('data-category-id'))"""
        )
        for cid in tabs:
            try:
                page.evaluate(
                    """(id) => {
                      const t = document.querySelector('.byn-tab-item[data-category-id="' + id + '"]');
                      if (t) t.click();
                    }""",
                    cid,
                )
                time.sleep(pause + 0.6)
                harvest()
                for _ in range(4):  # nudge down inside the section
                    page.mouse.wheel(0, step)
                    time.sleep(pause)
                    harvest()
            except Exception as e:
                print(f"tab {cid} skipped: {e}")

        # summary per category
        counts = {}
        for r in items.values():
            counts[r["category"]] = counts.get(r["category"], 0) + 1
        for c, n in counts.items():
            print(f"  {c}: {n}")
        browser.close()
    return list(items.values())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-o", "--output", default="menu.csv")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--step", type=int, default=500, help="scroll step in px")
    ap.add_argument("--pause", type=float, default=0.8, help="seconds between scrolls")
    ap.add_argument("--browser-path",
                    help="path to a Chrome/Chromium/Brave/Edge executable (auto-detected if omitted)")
    ap.add_argument("--min-items", type=int, default=1,
                    help="abort WITHOUT writing the CSV if fewer items are found")
    ap.add_argument("--full-size-images", action="store_true",
                    help="drop the 200x201 thumbnail prefix from image URLs")
    a = ap.parse_args()

    rows = scrape(a.url, a.headed, a.step, a.pause, a.full_size_images, a.browser_path)
    if len(rows) < a.min_items:
        sys.exit(f"Only {len(rows)} items found (min {a.min_items}); CSV not written.")

    # utf-8-sig so Excel shows Persian correctly; use encoding="utf-8" if you prefer
    with open(a.output, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["category", "name", "description", "price", "image"])
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} items to {a.output}")


if __name__ == "__main__":
    main()
