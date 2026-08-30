import json
import tempfile
import unittest
from pathlib import Path

from locate_comment import load_target


class LocateCommentTests(unittest.TestCase):
    def test_load_target_by_index_and_cid(self):
        rows = [{"cid": "a"}, {"cid": "b"}]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.json"
            path.write_text(json.dumps(rows), encoding="utf-8")
            self.assertEqual("a", load_target(path, index=1)["cid"])
            self.assertEqual("b", load_target(path, cid="b")["cid"])


if __name__ == "__main__":
    unittest.main()
