from pathlib import Path
from urllib.parse import urlencode

import requests
import truststore
from bs4 import BeautifulSoup


truststore.inject_into_ssl()

BASE_DIR = Path(__file__).resolve().parent
COVER_DIR = BASE_DIR / "static" / "kapaklar"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
SEARCH_URL = "https://www.kitapyurdu.com/index.php"


class ScraperError(Exception):
    pass


def _get(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        response.encoding = "utf-8"
        return response
    except requests.RequestException as exc:
        raise ScraperError(str(exc)) from exc


def _text(card, selector):
    element = card.select_one(selector)
    return element.get_text(" ", strip=True) if element else ""


def search_books(query):
    url = f"{SEARCH_URL}?{urlencode({'route': 'product/search', 'filter_name': query})}"
    response = _get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for card in soup.select(".ky-product")[:20]:
        title_link = card.select_one("a.ky-product-title")
        cover = card.select_one("a.ky-product-cover img")
        publisher_link = card.select_one(".ky-product-publisher a")
        if not title_link:
            continue

        detail_url = title_link.get("href", "")
        cover_url = cover.get("src") or cover.get("data-src") if cover else ""
        if cover_url and cover_url.startswith("//"):
            cover_url = "https:" + cover_url
        item = {
            "title": title_link.get_text(" ", strip=True),
            "author": _text(card, ".ky-product-author a"),
            "publisher": publisher_link.get_text(" ", strip=True) if publisher_link else "",
            "cover_url": cover_url,
            "url": detail_url,
            "total_pages": 0,
            "isbn": "",
            "publication_year": "",
        }
        try:
            details = get_book_details(detail_url)
            item.update(details)
        except ScraperError:
            pass
        results.append(item)
    return results


def get_book_details(url):
    if not url:
        return {}
    response = _get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    details = {}
    attribute_rows = soup.select(".ky-pd-attributes__item")
    if not attribute_rows:
        attribute_rows = soup.select("[class*='attribute']")
    for row in attribute_rows:
        if ":" not in row.get_text(" ", strip=True):
            continue
        parts = row.get_text(" ", strip=True).split(":", 1)
        if len(parts) != 2:
            continue
        label = parts[0].strip()
        text = parts[1].strip()
        if "Sayfa" in label:
            digits = "".join(character for character in text if character.isdigit())
            if digits:
                details["total_pages"] = int(digits)
        elif "ISBN" in label:
            details["isbn"] = text.split()[0]
        elif "Yayın Tarihi" in label:
            digits = "".join(character for character in text if character.isdigit())
            if len(digits) >= 4:
                details["publication_year"] = digits[-4:]

    for row in attribute_rows:
        label = row.get_text(" ", strip=True)
        value = row.select_one(".value")
        if not value:
            continue
        text = value.get_text(" ", strip=True)
        if "Sayfa Sayısı" in label:
            digits = "".join(character for character in text if character.isdigit())
            if digits:
                details["total_pages"] = int(digits)
        elif "ISBN" in label:
            details["isbn"] = text
        elif "Yayın Yılı" in label or "Basım Yılı" in label:
            digits = "".join(character for character in text if character.isdigit())
            if digits:
                details["publication_year"] = digits[:4]
    return details


def download_cover(url, book_id):
    if not url:
        return None
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        return None
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    content_type = response.headers.get("Content-Type", "")
    extension = ".png" if "png" in content_type else ".jpg"
    path = COVER_DIR / f"{book_id}{extension}"
    path.write_bytes(response.content)
    return f"/static/kapaklar/{path.name}"
