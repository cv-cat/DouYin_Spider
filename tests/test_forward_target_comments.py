import json
import tempfile
import unittest
from pathlib import Path

from forward_target_comments import load_targets, normalize_text, target_matches


class ForwardTargetTests(unittest.TestCase):
    def test_load_targets_deduplicates_and_limits(self):
        rows = [
            {"cid": "1", "nickname": " 小 余 ", "text": "你 好"},
            {"cid": "1", "nickname": "重复", "text": "重复"},
            {"cid": "2", "nickname": "用户二", "text": ""},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "targets.json"
            path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            targets = load_targets(path, 2)
        self.assertEqual(["1", "2"], [row["cid"] for row in targets])
        self.assertEqual("小余", targets[0]["nickname"])

    def test_match_requires_nickname_and_content(self):
        target = {"nickname": "小余", "text": "你好"}
        self.assertTrue(target_matches(target, "小余\n你 好\n1天前 · 湖北"))
        self.assertFalse(target_matches(target, "小余\n别的内容"))
        self.assertEqual("测试内容", normalize_text(" 测试\n内容 "))


if __name__ == "__main__":
    unittest.main()
