"""Collect a bounded public-comment sample for awesome-gpt-image-2 videos."""

import json
import os
from pathlib import Path

for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(name, None)

from collect_ip_comments import build_auth, collect_comments, deduplicate_rows


SAMPLES = (
    ("7667928603090981221", 50),
    ("7634186823861947702", 20),
    ("7633284706334805290", 10),
    ("7678401671558368531", 10),
    ("7678183017597181674", 10),
)


def main() -> None:
    auth = build_auth()
    all_rows = []
    sources = []
    for aweme_id, limit in SAMPLES:
        stats = {}
        rows, pages = collect_comments(
            auth,
            f"https://www.douyin.com/video/{aweme_id}",
            candidate_limit=limit,
            stats=stats,
        )
        for row in rows:
            row["source_aweme_id"] = aweme_id
        all_rows.extend(rows)
        sources.append({"aweme_id": aweme_id, "rows": len(rows), "pages": pages, "stats": stats})

    all_rows = deduplicate_rows(all_rows)
    output = Path("datas/awesome_gpt_image_2_comments_20260827.json")
    output.write_text(
        json.dumps({"sources": sources, "comment_count": len(all_rows), "comments": all_rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output.resolve()), "comment_count": len(all_rows), "sources": sources}))


if __name__ == "__main__":
    main()
