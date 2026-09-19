import contextlib
import gzip
import io
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from dy_live.pk import PKMessageHandler, decode_pk_message
from dy_live.server import DouyinLive
from static import Live_pb2, PK_pb2


# Sanitized wire captures, independently decoded by the browser on 2026-09-19.
# Kept original tags/values for scores and times; stripped unrelated fields,
# replaced IDs/names. These literals intentionally do not use our encoder.
START = bytes.fromhex(
    '0a1b108180daea81aad5a169188280daea81aad5a16920e4ceefc18b34124d108380daea81aad5a16918b3cbefc18b3420ac02308480daea81aad5a169c00201d2021337353835303030303030303030303030303033da021337353835303030303030303030303030303034')
SCORES = bytes.fromhex(
    '0a1b108580daea81aad5a169188280daea81aad5a16920e7d281c28b3410ca01408480daea81aad5a1698a012a08da01108680daea81aad5a1693a033231384001aa0113373538353030303030303030303030303030368a012a08d301108780daea81aad5a1693a033231314002aa011337353835303030303030303030303030303037c0068380daea81aad5a16992071337353835303030303030303030303030303033')
ARMIES = bytes.fromhex(
    '0a1b108880daea81aad5a169188280daea81aad5a16920b2d981c28b34124f088780daea81aad5a16912430a15088980daea81aad5a16910c6011a065669657765720a14088a80daea81aad5a16910051a065669657765720a14088b80daea81aad5a16910051a06566965776572124e088680daea81aad5a16912420a14088c80daea81aad5a16910631a065669657765720a14088d80daea81aad5a16910371a065669657765720a14088e80daea81aad5a16910071a06566965776572')
FINISH = bytes.fromhex(
    '0a1b108f80daea81aad5a169188280daea81aad5a1692088f581c28b34124d108380daea81aad5a16918b3cbefc18b3420ac02308480daea81aad5a169c00202d2021337353835303030303030303030303030303033da0213373538353030303030303030303030303030341aa101088780daea81aad5a169122a088980daea81aad5a169120656696577657220c6012a13373538353030303030303030303030303030391229088a80daea81aad5a169120656696577657220052a13373538353030303030303030303030303031301229088b80daea81aad5a169120656696577657220052a13373538353030303030303030303030303031311a13373538353030303030303030303030303030371aa001088680daea81aad5a1691229088c80daea81aad5a169120656696577657220632a13373538353030303030303030303030303031321229088d80daea81aad5a169120656696577657220372a13373538353030303030303030303030303031331229088e80daea81aad5a169120656696577657220072a13373538353030303030303030303030303031341a1337353835303030303030303030303030303036222a08da01108680daea81aad5a1694213373538353030303030303030303030303030367a03323138800101222a08d301108780daea81aad5a1694213373538353030303030303030303030303030377a03323131800102')
BATTLE = '7585000000000000003'
CHANNEL = '7585000000000000004'


def frame(items, compressed=False, ack=False):
    response = Live_pb2.LiveResponse(needAck=ack, internalExt='opaque-ack')
    for index, (method, payload) in enumerate(items, 1):
        response.messagesList.add(method=method, payload=payload, msgId=index)
    payload = response.SerializeToString()
    if compressed:
        payload = gzip.compress(payload)
    return Live_pb2.PushFrame(logId=9007199254741001, payloadType='msg',
                              payload=payload).SerializeToString()


class PKWireTest(unittest.TestCase):
    def test_real_wire_lifecycle_scores_and_exact_ids(self):
        start = decode_pk_message('WebcastLinkMicBattleMethod', START)
        scores = decode_pk_message('LinkMicMethod', SCORES)
        armies = decode_pk_message('WebcastLinkMicArmiesMethod', ARMIES)
        finish = decode_pk_message('LinkMicBattleFinishMethod', FINISH)
        self.assertEqual((start['battle_id'], start['channel_id']), (BATTLE, CHANNEL))
        self.assertEqual((start['type'], start['duration']), ('start', 300))
        self.assertEqual([s['score'] for s in scores['scores']], ['218', '211'])
        self.assertEqual([s['anchor_id'] for s in scores['scores']],
                         ['7585000000000000006', '7585000000000000007'])
        self.assertIsNone(armies['battle_id'])
        self.assertFalse(armies['is_complete'])
        users = armies['anchors'][0]['users']
        self.assertEqual([u['score'] for u in users], ['99', '55', '7'])
        self.assertEqual([u['uid'] for u in users],
                         ['7585000000000000012', '7585000000000000013', '7585000000000000014'])
        self.assertEqual(users[0]['nickname'], 'Viewer')
        self.assertEqual(finish['battle_id'], BATTLE)
        self.assertEqual(finish['scores'], scores['scores'])
        self.assertEqual(sorted(finish['anchors'], key=lambda a: a['anchor_id']), armies['anchors'])

    def test_aliases_dedup_finish_and_stale_armies(self):
        handler = PKMessageHandler()
        self.assertIsNone(handler.handle('LinkMicArmiesMethod', ARMIES)['context_battle_id'])
        handler.handle('LinkMicBattleMethod', START)
        event = handler.handle('WebcastLinkMicArmiesMethod', ARMIES, 99)
        self.assertEqual(event['context_battle_id'], BATTLE)
        self.assertIsNone(event['battle_id'])
        self.assertIsNone(handler.handle('LinkMicArmiesMethod', ARMIES, 99))
        handler.handle('WebcastLinkMicBattleFinishMethod', FINISH)
        self.assertIsNone(handler.handle('LinkMicBattleFinishMethod', FINISH, 100))
        reordered = PK_pb2.LinkMicBattleFinish.FromString(FINISH)
        reordered.battle_armies.reverse()
        reordered.battle_scores.reverse()
        self.assertIsNone(handler.handle('LinkMicBattleFinishMethod', reordered.SerializeToString(), 102))
        self.assertIsNone(handler.handle('LinkMicArmiesMethod', ARMIES, 101)['context_battle_id'])
        # A new battle shares the same channel; old armies must not acquire it.
        newer = PK_pb2.LinkMicBattle.FromString(START)
        newer.common.msg_id = 200
        newer.battle_settings.battle_id += 100
        newer.battle_settings.battle_id_str = str(newer.battle_settings.battle_id)
        newer.battle_settings.start_time_ms += 400000
        handler.handle('LinkMicBattleMethod', newer.SerializeToString())
        stale = handler.handle('LinkMicArmiesMethod', ARMIES, 201)
        self.assertIsNone(stale['context_battle_id'])
        handler.handle('LinkMicMethod', SCORES, 202)
        self.assertEqual(handler.active['battle_id'], str(int(BATTLE) + 100))

    def test_unknown_play_mode_is_not_an_empty_complete_rank(self):
        event = decode_pk_message('LinkMicArmiesMethod', b'\x22\x02\x08\x01')
        self.assertTrue(event['has_unsupported_rank_list_v2'])
        self.assertFalse(event['is_complete'])
        self.assertIsNone(decode_pk_message('LinkMicMethod', b'\x10\x64'))
        self.assertIsNone(decode_pk_message('WebcastChatMessage', b'anything'))

    def test_explicit_string_ids_win(self):
        finish = PK_pb2.LinkMicBattleFinish.FromString(FINISH)
        finish.battle_armies[0].rank_list[0].user_id = 1
        event = decode_pk_message('LinkMicBattleFinishMethod', finish.SerializeToString())
        self.assertEqual(event['anchors'][0]['users'][0]['uid'], '7585000000000000009')


class PKDispatchTest(unittest.TestCase):
    def test_gzip_and_plain_frames_ack_callback_and_print(self):
        for compressed in (False, True):
            with self.subTest(compressed=compressed):
                events = []
                auth = SimpleNamespace(live_websocket_verified=False)
                client = DouyinLive('123', auth, on_pk_event=events.append)
                ws = Mock()
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    client.on_message(ws, frame([
                        ('WebcastLinkMicBattleMethod', START),
                        ('WebcastLinkMicMethod', SCORES),
                        ('LinkMicArmiesMethod', ARMIES),
                        ('WebcastLinkMicBattleFinishMethod', FINISH),
                    ], compressed=compressed, ack=True))
                self.assertEqual([e['type'] for e in events], ['start', 'scores', 'armies', 'finish'])
                self.assertTrue(auth.live_websocket_verified)
                printed = output.getvalue()
                self.assertIn('[PK 开始]', printed)
                self.assertIn('[PK 贡献前三]', printed)
                self.assertIn('UID=7585000000000000012 Viewer PK值=99', printed)
                self.assertIn('[PK 结束]', printed)
                ack = Live_pb2.PushFrame.FromString(ws.send.call_args.args[0])
                self.assertEqual((ack.payloadType, ack.payload, ack.logId),
                                 ('ack', b'opaque-ack', 9007199254741001))

    def test_bad_pk_item_does_not_hide_later_chat_or_pk(self):
        events = []
        client = DouyinLive('123', SimpleNamespace(), on_pk_event=events.append)
        chat = Live_pb2.ChatMessage(content='hello')
        chat.user.nickname = 'Tester'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            client.on_message(Mock(), frame([
                ('LinkMicArmiesMethod', b'\x12\x80'),
                ('WebcastChatMessage', chat.SerializeToString()),
                ('LinkMicMethod', SCORES),
            ]))
        self.assertEqual([e['type'] for e in events], ['scores'])
        self.assertIn('[PK 消息处理失败]', output.getvalue())
        self.assertIn('hello', output.getvalue())

    def test_heartbeat_and_empty_frames_are_ignored(self):
        auth = SimpleNamespace(live_websocket_verified=False)
        client = DouyinLive('123', auth, on_pk_event=Mock())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            client.on_message(Mock(), Live_pb2.PushFrame(payloadType='hb', payload=b'ping').SerializeToString())
            client.on_message(Mock(), Live_pb2.PushFrame().SerializeToString())
        client.on_pk_event.assert_not_called()
        self.assertFalse(auth.live_websocket_verified)
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
