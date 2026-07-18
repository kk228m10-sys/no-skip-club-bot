"""
Скачивает каталог упражнений с sportkuznica.com/Exe/
и сохраняет JSON: название, url страницы, ссылка на видео (если есть), описание, теги.
"""

from __future__ import annotations

import json
import re
import time
import urllib.request
from pathlib import Path

BASE = "https://sportkuznica.com"
CATALOG = f"{BASE}/Exe/"
OUT = Path(__file__).resolve().parent.parent / "data" / "sportkuznica_exercises.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def find_item_links(html: str) -> list[tuple[str, str]]:
    """Возвращает [(id, title), ...] с страницы каталога."""
    # <a href="/Exe/Item/1358/"> ... title ...
    pattern = re.compile(
        r'href="(/Exe/Item/(\d+)/)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,120})',
        re.I | re.S,
    )
    seen = {}
    for m in pattern.finditer(html):
        path, item_id, title = m.group(1), m.group(2), re.sub(r"\s+", " ", m.group(3)).strip()
        if not title or title.lower() in ("подробнее...", "в каталог упражнений"):
            continue
        if item_id not in seen:
            seen[item_id] = title
    return [(i, seen[i]) for i in seen]


def extract_video(html: str) -> dict:
    result = {
        "youtube_id": None,
        "youtube_url": None,
        "vk_url": None,
        "iframe_src": None,
        "video_src": None,
        "mp4": None,
    }

    # YouTube
    yt = re.search(
        r"(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})",
        html,
        re.I,
    )
    if yt:
        result["youtube_id"] = yt.group(1)
        result["youtube_url"] = f"https://www.youtube.com/watch?v={yt.group(1)}"

    # VK
    vk = re.search(r'(https?://(?:vk\.com|vkvideo\.ru)/[^\s"\'<>]+)', html, re.I)
    if vk:
        result["vk_url"] = vk.group(1).replace("&amp;", "&")

    # iframe
    for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I):
        src = m.group(1).replace("&amp;", "&")
        if any(x in src.lower() for x in ("youtube", "youtu", "vk", "vimeo", "rutube", "video")):
            result["iframe_src"] = src
            break
    if not result["iframe_src"]:
        m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I)
        if m:
            result["iframe_src"] = m.group(1).replace("&amp;", "&")

    # video / source
    m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if m:
        result["video_src"] = m.group(1)
    m = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if m:
        result["video_src"] = m.group(1)

    mp4 = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html, re.I)
    if mp4:
        result["mp4"] = mp4.group(1)

    # data attributes often used by players
    for attr in ("data-video", "data-src", "data-url", "data-file", "data-id"):
        m = re.search(rf'{attr}=["\']([^"\']+)["\']', html, re.I)
        if m and ("video" in m.group(1).lower() or "youtu" in m.group(1).lower() or m.group(1).isdigit()):
            result[attr] = m.group(1)

    return result


def extract_meta(html: str) -> dict:
    def grab_section(label: str) -> list[str]:
        # Блоки вида: <div class="header"><span>Место</span></div>
        # затем <div class="i level" title="Зал"><span>Зал</span></div>
        m = re.search(
            rf'<div class="header"><span>{re.escape(label)}</span></div>\s*(.*?)</div>\s*</div>',
            html,
            re.I | re.S,
        )
        if not m:
            # fallback: от label до следующего header
            m = re.search(
                rf'<span>{re.escape(label)}</span></div>\s*(.*?)(?:<div class="header"|Основная нагрузка|Программы)',
                html,
                re.I | re.S,
            )
        if not m:
            return []
        chunk = m.group(1)
        titles = re.findall(r'title="([^"]+)"', chunk)
        # убрать дубли, сохранить порядок
        seen = set()
        out = []
        for t in titles:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out[:20]

    def grab_muscles() -> list[str]:
        m = re.search(
            r"Основная нагрузка</h3>(.*?)(?:</section>|Альтернативные|Программы с упражнением|Комплексы)",
            html,
            re.I | re.S,
        )
        if not m:
            return []
        titles = re.findall(r'title="([^"]+)"', m.group(1))
        seen, out = set(), []
        for t in titles:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out[:25]

    # meta description — короткий чистый текст
    desc = ""
    m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if m:
        desc = m.group(1).strip()
    if not desc:
        # основной текст на странице (после h1 / в контенте)
        m = re.search(
            r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>',
            html,
            re.I | re.S,
        )
        if m:
            text = re.sub(r"<[^>]+>", " ", m.group(1))
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 40:
                desc = text[:1500]

    return {
        "gender": grab_section("Пол"),
        "place": grab_section("Место"),
        "difficulty": grab_section("Сложность"),
        "equipment": grab_section("Снаряды"),
        "effort": grab_section("Тип усилий"),
        "muscles": grab_muscles() or grab_section("Основная нагрузка"),
        "description": desc,
    }


def parse_item(item_id: str, title_hint: str = "") -> dict:
    url = f"{BASE}/Exe/Item/{item_id}/"
    html = fetch(url)
    # title
    title = title_hint
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        title = re.sub(r"<[^>]+>", "", m.group(1))
        title = re.sub(r"\s+", " ", title).strip()
    video = extract_video(html)
    meta = extract_meta(html)
    return {
        "id": item_id,
        "title": title,
        "url": url,
        **video,
        **meta,
    }


def scrape_catalog() -> list[dict]:
    items: dict[str, str] = {}
    # pages 1..15 should cover 11 pages
    for page in range(1, 16):
        url = CATALOG if page == 1 else f"{CATALOG}?p={page}"
        print(f"catalog page {page}: {url}")
        try:
            html = fetch(url)
        except Exception as e:
            print(f"  fail: {e}")
            break
        found = find_item_links(html)
        if not found:
            print("  no items, stop")
            break
        new = 0
        for item_id, title in found:
            if item_id not in items:
                items[item_id] = title
                new += 1
        print(f"  found {len(found)}, new {new}, total unique {len(items)}")
        if new == 0 and page > 1:
            break
        time.sleep(0.4)

    results = []
    total = len(items)
    for i, (item_id, title) in enumerate(items.items(), 1):
        print(f"[{i}/{total}] item {item_id}: {title[:50]}")
        try:
            results.append(parse_item(item_id, title))
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({"id": item_id, "title": title, "url": f"{BASE}/Exe/Item/{item_id}/", "error": str(e)})
        time.sleep(0.35)
    return results


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    results = scrape_catalog()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    with_video = sum(
        1
        for r in results
        if r.get("youtube_url") or r.get("vk_url") or r.get("iframe_src") or r.get("mp4") or r.get("video_src")
    )
    print(f"\nSaved {len(results)} exercises to {OUT}")
    print(f"With video link: {with_video}")


if __name__ == "__main__":
    main()
