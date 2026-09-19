import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dy_apis.douyin_api import DouyinAPI, LivePKAPIError


def fake_sign(params, data=None, host='www.douyin.com'):
    params.add_param('a_bogus', f'signed-for:{host}')
    return params


class LivePKAPITest(unittest.TestCase):
    def setUp(self):
        self.auth = SimpleNamespace(msToken='test-token', cookie={})
        # Same JSON shape and large numeric IDs as captured PC Web responses.
        self.room = {'status_code': 0, 'data': {'data': [{
            'id_str': '7687099550015753000',
            'owner': {'id_str': '1565319530819928', 'nickname': '主播'},
            'linker_map': {'1': 7687114086841259023},
        }]}}
        self.snapshot = {'status_code': 0, 'data': {'battle_stats': {
            'battle_settings': {
                'battle_id_str': '7687114318937084966',
                'channel_id_str': '7687114086841259023', 'finished': 0,
            },
            'user_infos': {'7585857326805287985': {'user': {
                'user_id_str': '7585857326805287985', 'nick_name': '对手',
            }, 'room_id': '7687000000000000001'}},
        }}}

    @patch('dy_apis.douyin_api.Params.with_a_bogus', fake_sign)
    def test_rank_wire_contract_and_business_error_preserved(self):
        denied = {'status_code': 20003, 'data': {'message': "User doesn't login"}}
        self.auth.request = Mock(return_value=Mock(
            text='{}', headers={}, json=Mock(return_value=denied)))
        response = DouyinAPI.get_live_pk_contribution_rank(
            self.auth, '7687114086841259023', '7585857326805287985',
            web_rid='403309276429', timeout=7,
        )
        self.assertEqual(response, denied)
        args, kwargs = self.auth.request.call_args
        self.assertEqual(args, ('GET',
            'https://live.douyin.com/webcast/linkmic/battle/ranklist_armies/'))
        params = kwargs['params']
        self.assertEqual(params['channel_id'], '7687114086841259023')
        self.assertEqual(params['anchor_id'], '7585857326805287985')
        self.assertEqual(params['msToken'], 'test-token')
        self.assertEqual(params['a_bogus'], 'signed-for:live.douyin.com')
        self.assertEqual(params['enter_from'], 'link_share')
        self.assertEqual(kwargs['headers']['referer'], 'https://live.douyin.com/403309276429')
        self.assertEqual(kwargs['timeout'], 7)
        for key in ('battle_id', 'room_id', 'offset', 'count', 'webcast_sdk_version'):
            self.assertNotIn(key, params)

    def test_url_discovery_both_sides_and_raw_zero_scores(self):
        rank = {'status_code': 0, 'data': {'users': [{
            'user': {'id_str': '7585857326805287985', 'nickname': '贡献用户'},
            'score': 0, 'score_blur_text': '',
        }], 'contributer_total_uv': 1}}
        with patch.object(DouyinAPI, '_get_live_web', side_effect=[
            self.room, self.snapshot, rank, rank, self.room, self.snapshot,
        ]) as request:
            result = DouyinAPI.get_live_pk_rank(
                self.auth, 'https://live.douyin.com/403309276429?from=test', side='both')
        self.assertEqual(result['state'], 'ok')
        self.assertEqual(result['context']['web_rid'], '403309276429')
        self.assertEqual(result['context']['channel_id'], '7687114086841259023')
        self.assertEqual(result['context']['anchors'][1]['nickname'], '对手')
        self.assertEqual(set(result['ranks']), {'1565319530819928', '7585857326805287985'})
        self.assertEqual(result['ranks']['7585857326805287985'], rank)
        self.assertEqual(request.call_count, 6)

    def test_no_battle_does_not_query_rank(self):
        with patch.object(DouyinAPI, '_get_live_web', side_effect=[
            self.room, {'status_code': 0, 'data': {}},
        ]) as request:
            result = DouyinAPI.get_live_pk_rank(self.auth, '403309276429')
        self.assertEqual(result['state'], 'not_in_pk')
        self.assertEqual(result['ranks'], {})
        self.assertEqual(request.call_count, 2)

    def test_no_channel_does_not_query_snapshot(self):
        room = copy.deepcopy(self.room)
        room['data']['data'][0]['linker_map'] = {}
        with patch.object(DouyinAPI, '_get_live_web', return_value=room) as request:
            result = DouyinAPI.get_live_pk_rank(self.auth, '403309276429')
        self.assertEqual(result['state'], 'not_in_pk')
        self.assertEqual(request.call_count, 1)

    def test_context_error_not_confused_with_no_pk(self):
        denied = {'status_code': 20003, 'data': {'message': 'login required'}}
        with patch.object(DouyinAPI, '_get_live_web', return_value=denied):
            with self.assertRaises(LivePKAPIError) as raised:
                DouyinAPI.get_live_pk_rank(self.auth, '403309276429')
        self.assertEqual(raised.exception.status_code, 20003)
        self.assertEqual(raised.exception.response, denied)

    def test_same_channel_new_battle_marks_result_unusable(self):
        after = copy.deepcopy(self.snapshot)
        after['data']['battle_stats']['battle_settings']['battle_id_str'] = '7687114318937084967'
        rank = {'status_code': 0, 'data': {'users': []}}
        with patch.object(DouyinAPI, '_get_live_web', side_effect=[
            self.room, self.snapshot, rank, self.room, after,
        ]):
            result = DouyinAPI.get_live_pk_rank(self.auth, '403309276429')
        self.assertEqual(result['state'], 'context_changed')
        self.assertNotEqual(result['context']['battle_id'], result['context_after']['battle_id'])

    def test_rank_error_preserved_by_convenience_api(self):
        denied = {'status_code': 20003, 'data': {'message': 'login required'}}
        with patch.object(DouyinAPI, '_get_live_web', side_effect=[
            self.room, self.snapshot, denied, self.room, self.snapshot,
        ]):
            result = DouyinAPI.get_live_pk_rank(self.auth, '403309276429')
        self.assertEqual(result['state'], 'api_error')
        self.assertEqual(result['ranks']['1565319530819928'], denied)

    def test_invalid_room_or_side_rejected_before_network(self):
        with patch.object(DouyinAPI, '_get_live_web') as request:
            for value in ('https://example.com/123', '1e20', 'https://live.douyin.com/abc'):
                with self.assertRaises(ValueError):
                    DouyinAPI.get_live_pk_rank(self.auth, value)
            with self.assertRaises(ValueError):
                DouyinAPI.get_live_pk_rank(self.auth, '123', side='invalid')
            request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
