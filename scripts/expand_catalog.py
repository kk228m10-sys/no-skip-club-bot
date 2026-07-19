#!/usr/bin/env python3
"""Расширяет каталог видео: sportkuznica + упражнения из планов + библиотека."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DATA = ROOT / "data" / "sportkuznica_exercises.json"
OUT_BUNDLED = ROOT / "bundled_data" / "sportkuznica_exercises.json"
PLANS = ROOT / "bundled_data" / "training_plans.json"
BASE = "https://sportkuznica.com"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def scrape_all_ids() -> dict[str, str]:
    items: dict[str, str] = {}
    for page in range(1, 20):
        url = f"{BASE}/Exe/" if page == 1 else f"{BASE}/Exe/?p={page}"
        print(f"page {page}: {url}")
        try:
            html = fetch(url)
        except Exception as e:
            print("  fail", e)
            break
        found = re.findall(
            r'href="(/Exe/Item/(\d+)/)"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,120})',
            html,
            re.I | re.S,
        )
        new = 0
        for _path, item_id, title in found:
            title = re.sub(r"\s+", " ", title).strip()
            if not title or title.lower() in ("подробнее...", "в каталог упражнений"):
                continue
            if item_id not in items:
                items[item_id] = title
                new += 1
        # also bare ids
        for item_id in re.findall(r"/Exe/Item/(\d+)/", html):
            items.setdefault(item_id, items.get(item_id) or f"Упражнение {item_id}")
        print(f"  new={new} total={len(items)}")
        if page > 1 and new == 0:
            break
        time.sleep(0.3)
    return items


def extract_video(html: str) -> dict:
    result = {
        "youtube_id": None,
        "youtube_url": None,
        "vk_url": None,
        "iframe_src": None,
        "video_src": None,
        "mp4": None,
    }
    yt = re.search(
        r"(?:youtube\.com/embed/|youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})",
        html,
        re.I,
    )
    if yt:
        result["youtube_id"] = yt.group(1)
        result["youtube_url"] = f"https://www.youtube.com/watch?v={yt.group(1)}"
    vk = re.search(r'(https?://(?:vk\.com|vkvideo\.ru)/[^\s"\'<>]+)', html, re.I)
    if vk:
        result["vk_url"] = vk.group(1).replace("&amp;", "&")
    for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I):
        src = m.group(1).replace("&amp;", "&")
        if any(x in src.lower() for x in ("youtube", "youtu", "vk", "vimeo", "rutube", "video")):
            result["iframe_src"] = src
            break
    m = re.search(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I)
    if m:
        result["video_src"] = m.group(1)
    mp4 = re.search(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)', html, re.I)
    if mp4:
        result["mp4"] = mp4.group(1)
    return result


def parse_item(item_id: str, title_hint: str = "") -> dict:
    url = f"{BASE}/Exe/Item/{item_id}/"
    html = fetch(url)
    title = title_hint
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
    video = extract_video(html)
    desc = ""
    m = re.search(r'<meta\s+name="description"\s+content="([^"]+)"', html, re.I)
    if m:
        desc = m.group(1).strip()
    return {
        "id": str(item_id),
        "title": title or f"Упражнение {item_id}",
        "url": url,
        "description": desc,
        "place": [],
        "difficulty": [],
        "equipment": [],
        **video,
        "source": "sportkuznica",
    }


def walk_plans(obj, out: list):
    if isinstance(obj, list):
        for x in obj:
            walk_plans(x, out)
    elif isinstance(obj, dict):
        if obj.get("name") and (obj.get("video_url") or obj.get("sets_display") or obj.get("sets") or obj.get("rest") is not None or obj.get("alt") is not None):
            out.append(obj)
        for v in obj.values():
            walk_plans(v, out)


def plan_entries(existing_titles: set[str]) -> list[dict]:
    if not PLANS.exists():
        return []
    plans = json.loads(PLANS.read_text(encoding="utf-8"))
    rows = []
    walk_plans(plans, rows)
    by_title: dict[str, dict] = {}
    for r in rows:
        name = (r.get("name") or "").strip()
        url = (r.get("video_url") or "").strip()
        if not name or not url:
            continue
        key = name.lower().replace("ё", "е")
        if key in existing_titles:
            continue
        if key not in by_title:
            by_title[key] = r
    out = []
    for key, r in by_title.items():
        name = r["name"].strip()
        url = r["video_url"].strip()
        hid = "plan-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:10]
        item = {
            "id": hid,
            "title": name,
            "url": url,
            "description": "Из планов тренировок No Skip Club",
            "place": [],
            "difficulty": [],
            "equipment": [],
            "source": "training_plans",
        }
        if "youtu" in url:
            item["youtube_url"] = url
            m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
            if m:
                item["youtube_id"] = m.group(1)
        elif "vk" in url:
            item["vk_url"] = url
        else:
            item["iframe_src"] = url
        out.append(item)
    return out


def library_entries(existing_titles: set[str]) -> list[dict]:
    try:
        from content import EXERCISE_LIBRARY
        import video_catalog as vc

        vc.load_catalog(force=True)
        vc.bind_library_videos(EXERCISE_LIBRARY)
    except Exception as e:
        print("library bind skip", e)
        return []
    out = []
    for place, levels in EXERCISE_LIBRARY.items():
        if not isinstance(levels, dict):
            continue
        for level, exercises in levels.items():
            if not isinstance(exercises, list):
                continue
            for ex in exercises:
                if not isinstance(ex, dict):
                    continue
                name = (ex.get("name") or "").strip()
                url = (ex.get("video_url") or "").strip()
                if not name:
                    continue
                key = name.lower().replace("ё", "е")
                if key in existing_titles:
                    continue
                if not url:
                    video = vc.find_video(name, place=place)
                    url = (video or {}).get("video_url") or ""
                if not url:
                    continue
                existing_titles.add(key)
                hid = "lib-" + hashlib.md5(f"{place}:{level}:{name}".encode()).hexdigest()[:10]
                item = {
                    "id": hid,
                    "title": name,
                    "url": url,
                    "description": (ex.get("technique") or "")[:500],
                    "place": [place],
                    "difficulty": [level],
                    "equipment": [],
                    "source": "exercise_library",
                    "youtube_url": url if "youtu" in url else None,
                    "iframe_src": url if "youtu" not in url else None,
                }
                out.append(item)
    return out


def main():
    print("=== scrape sportkuznica listing ===")
    listing = scrape_all_ids()
    base_items = []
    # reuse existing full scrape if same ids to save time
    old = []
    if OUT_DATA.exists():
        old = json.loads(OUT_DATA.read_text(encoding="utf-8"))
    old_by_id = {str(x.get("id")): x for x in old if isinstance(x, dict) and x.get("id")}

    total = len(listing)
    for i, (item_id, title) in enumerate(listing.items(), 1):
        if item_id in old_by_id and not old_by_id[item_id].get("error"):
            prev = old_by_id[item_id]
            has_v = any(prev.get(k) for k in ("youtube_url", "vk_url", "iframe_src", "mp4", "video_src"))
            if has_v:
                prev = dict(prev)
                prev["source"] = "sportkuznica"
                base_items.append(prev)
                print(f"[{i}/{total}] reuse {item_id}")
                continue
        print(f"[{i}/{total}] fetch {item_id}: {title[:40]}")
        try:
            base_items.append(parse_item(item_id, title))
        except Exception as e:
            print("  ERR", e)
            base_items.append(
                {
                    "id": item_id,
                    "title": title,
                    "url": f"{BASE}/Exe/Item/{item_id}/",
                    "error": str(e),
                    "source": "sportkuznica",
                }
            )
        time.sleep(0.25)

    titles = {re.sub(r"\s+", " ", (x.get("title") or "").lower().replace("ё", "е")) for x in base_items}
    print("base", len(base_items))

    print("=== add from training plans ===")
    plans = plan_entries(titles)
    print("plan extras", len(plans))
    for p in plans:
        titles.add(re.sub(r"\s+", " ", p["title"].lower().replace("ё", "е")))

    # temporarily write base so video_catalog can load it for library bind
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_BUNDLED.parent.mkdir(parents=True, exist_ok=True)
    merged = base_items + plans
    OUT_DATA.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_BUNDLED.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=== add from exercise library ===")
    # reset video_catalog cache
    import importlib
    import video_catalog as vc

    importlib.reload(vc)
    lib = library_entries(titles)
    print("library extras", len(lib))
    merged = base_items + plans + lib

    # dedupe by title keep first
    seen = set()
    final = []
    for item in merged:
        if item.get("error") and not any(item.get(k) for k in ("youtube_url", "vk_url", "iframe_src", "mp4", "video_src")):
            continue
        t = re.sub(r"\s+", " ", (item.get("title") or "").lower().replace("ё", "е"))
        if not t or t in seen:
            continue
        seen.add(t)
        final.append(item)

    OUT_DATA.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_BUNDLED.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    with_v = sum(
        1
        for r in final
        if r.get("youtube_url") or r.get("vk_url") or r.get("iframe_src") or r.get("mp4") or r.get("video_src")
    )
    print(f"\nSAVED {len(final)} items, with video {with_v}")
    print("sources:", {s: sum(1 for x in final if x.get("source") == s) for s in ("sportkuznica", "training_plans", "exercise_library")})


if __name__ == "__main__":
    main()
