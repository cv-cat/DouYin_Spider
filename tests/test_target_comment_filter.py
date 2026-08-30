import unittest

from target_comment_filter import evaluate_target_comment, has_target_intent


class TargetCommentFilterTests(unittest.TestCase):
    def assert_rejected(self, text, nickname="正常昵称"):
        accepted, reasons = evaluate_target_comment({"text": text, "nickname": nickname})
        self.assertFalse(accepted, reasons)

    def assert_accepted(self, text, nickname="正常昵称"):
        accepted, reasons = evaluate_target_comment({"text": text, "nickname": nickname})
        self.assertTrue(accepted, reasons)

    def test_rejects_non_hubei_dating_target(self):
        self.assert_rejected("02郑州的有人谈吗")
        self.assert_rejected("南阳有吗")

    def test_rejects_pre_2000_birth_year_and_low_information(self):
        self.assert_rejected("98年的")
        self.assert_rejected("93")
        self.assert_rejected("86年")
        self.assert_rejected("94的")
        self.assert_rejected("97 来一个")

    def test_keeps_2000_or_later_birth_year(self):
        self.assert_accepted("02年，想认真认识一个湖北本地人")
        self.assert_accepted("我是00年的，武汉工作")

    def test_rejects_strong_male_signals(self):
        self.assert_rejected("蹲姐姐")
        self.assert_rejected("想找个甜妹")
        self.assert_rejected("许愿不抽烟不喝酒不纹身的女生")
        self.assert_rejected("有04的女生吗，我04")
        self.assert_rejected("认真找对象", nickname="武汉大叔")
        self.assert_rejected("有没有07的", nickname="每天吃肉的狂拽男人")

    def test_rejects_explicit_negative_intent(self):
        self.assert_rejected("别找了，单着不好吗")
        self.assert_rejected("我不需要对象，因为我是")
        self.assert_rejected("反正不找，找不到就和自己过")
        self.assert_rejected("骗你的主动我也不要，单身我的钱包都是满满的")

    def test_rejects_low_value_natural_interactions(self):
        self.assert_rejected("你好")
        self.assert_rejected("累了")
        self.assert_rejected("[尬笑][尬笑]")
        self.assert_rejected("@小雨")
        self.assert_rejected("哈哈哈")

    def test_rejects_additional_explicit_male_signal(self):
        self.assert_rejected("我是爷们!")

    def test_rejects_natural_but_non_target_comment(self):
        self.assert_rejected("我的面子怎么办")
        self.assert_rejected("对呀对呀")

    def test_identifies_usable_customer_intent(self):
        self.assertTrue(has_target_intent({"text": "家里已经开始给我介绍了"}))
        self.assertTrue(has_target_intent({"text": "02年，武汉工作"}))
        self.assertTrue(has_target_intent({"text": "怎么没人追我，我很好追的"}))
        self.assertFalse(has_target_intent({"text": "吃鸡王者"}))

    def test_keeps_ambiguous_natural_comment(self):
        self.assert_accepted("村里都在给我介绍五保户了")
        self.assert_accepted("真的，家里已经开始催了")


if __name__ == "__main__":
    unittest.main()
