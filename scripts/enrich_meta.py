"""Перепарсить meta (place/equipment/description) для уже скачанного JSON."""

from __future__ import annotations

import json
import time
from pathlib import Path

from scrape_sportkuznica import fetch, extract_meta, extract_video

DATA = Path(__file__).resolve().parent.parent / "data" / "sportkuznica_exercises.json"


def main():
    items = json.loads(DATA.read_text(encoding="utf-8"))
    total = len(items)
    for i, item in enumerate(items, 1):
        url = item.get("url") or f"https://sportkuznica.com/Exe/Item/{item['id']}/"
        print(f"[{i}/{total}] {item.get('title', '')[:50]}")
        try:
            html = fetch(url)
            meta = extract_meta(html)
            video = extract_video(html)
            item.update(meta)
            # не затирать youtube если уже есть
            for k, v in video.items():
                if v and not item.get(k):
                    item[k] = v
                elif v and k in ("youtube_id", "youtube_url", "iframe_src"):
                    item[k] = v
        except Exception as e:
            print(f"  err: {e}")
        time.sleep(0.25)

    DATA.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    with_place = sum(1 for x in items if x.get("place"))
    with_desc = sum(1 for x in items if x.get("description"))
    print(f"done. with place={with_place}, with desc={with_desc}")


if __name__ == "__main__":
    main()
