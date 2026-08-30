from __future__ import annotations

import json
from pathlib import Path

import yaml

from clean_dating_yaml_round2 import reason


path = Path("datas/douyin_comments_7672652235175692729_by_ip.yml")
payload = yaml.safe_load(path.read_text(encoding="utf-8"))
rows = [row for values in payload["comments_by_ip"].values() for row in values]
ids = [str(row.get("comment_id") or "") for row in rows]
expected_removed = {
    "7673430474090464049",
    "7673395848214004486",
    "7673380411520009009",
    "7673360198295585593",
    "7673326838438183738",
    "7673290160754426633",
    "7673268517626708770",
}
remaining_hits = [
    {"comment_id": row.get("comment_id"), "content": row.get("content"), "reason": reason(row)}
    for row in rows if reason(row)
]
print(json.dumps({
    "metadata_total": payload["metadata"]["total_comments"],
    "actual_total": len(rows),
    "ip_values": sorted({row.get("ip_location") for row in rows}),
    "duplicate_comment_ids": len(ids) - len(set(ids)),
    "expected_example_ids_still_present": sorted(expected_removed & set(ids)),
    "remaining_rule_hit_count": len(remaining_hits),
    "remaining_rule_hits": remaining_hits[:20],
}, ensure_ascii=False, indent=2))
