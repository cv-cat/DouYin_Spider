from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from finalize_chinese_comments_yml import spaced_yaml


HUBEI_LOCATIONS_EXCEPT_WUHAN = (
    # 黄石
    "黄石", "大冶", "阳新", "黄石港", "西塞山", "下陆", "铁山",
    # 十堰
    "十堰", "丹江口", "郧阳", "郧西", "竹山", "竹溪", "房县", "茅箭", "张湾",
    # 宜昌
    "宜昌", "宜都", "枝江", "当阳", "远安", "兴山", "秭归", "长阳", "五峰",
    "夷陵", "西陵", "伍家岗", "点军", "猇亭",
    # 襄阳
    "襄阳", "老河口", "枣阳", "宜城", "南漳", "谷城", "保康", "襄州", "樊城", "襄城",
    # 鄂州
    "鄂州", "鄂城", "华容", "梁子湖",
    # 荆门
    "荆门", "京山", "钟祥", "沙洋", "东宝", "掇刀",
    # 孝感
    "孝感", "汉川", "应城", "安陆", "云梦", "孝昌", "大悟", "孝南",
    # 荆州
    "荆州", "洪湖", "监利", "石首", "松滋", "江陵", "公安", "沙市",
    # 黄冈
    "黄冈", "麻城", "武穴", "团风", "红安", "罗田", "英山", "浠水", "蕲春", "黄梅", "黄州",
    # 咸宁
    "咸宁", "赤壁", "嘉鱼", "通城", "崇阳", "通山", "咸安",
    # 随州
    "随州", "广水", "随县", "曾都",
    # 恩施州
    "恩施", "利川", "建始", "巴东", "宣恩", "咸丰", "来凤", "鹤峰",
    # 省直管县级行政区
    "仙桃", "潜江", "天门", "神农架",
)


def matched_cities(row: dict) -> list[str]:
    content = str(row.get("评论内容") or "")
    return [place for place in HUBEI_LOCATIONS_EXCEPT_WUHAN if place in content]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    path = Path(args.path).resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows = payload["符合条件的评论"]
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.before-city-clean-{timestamp}{path.suffix}")
    shutil.copy2(path, backup)
    removed = [
        {"删除原因": f"评论自报武汉以外湖北地名：{'、'.join(matched_cities(row))}", **row}
        for row in rows if matched_cities(row)
    ]
    kept = [row for row in rows if not matched_cities(row)]
    payload["当前符合条件的评论数"] = len(kept)
    payload["符合条件的评论"] = kept
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120)
    path.write_text(spaced_yaml(rendered), encoding="utf-8")
    audit = path.with_name(f"{path.stem}.removed-cities-{timestamp}.yml")
    audit.write_text(yaml.safe_dump({"删除数量": len(removed), "删除记录": removed}, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
    print(yaml.safe_dump({"清洗前": len(rows), "删除": len(removed), "剩余": len(kept), "备份": str(backup), "审计": str(audit)}, allow_unicode=True, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
