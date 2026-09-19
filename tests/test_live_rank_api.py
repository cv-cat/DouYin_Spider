import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from dy_apis.douyin_api import DouyinAPI


def fake_sign(params, data=None, host='www.douyin.com'):
    params.add_param('a_bogus', f'signed-for:{host}')
    return params


class LiveRankAPITest(unittest.TestCase):
    def setUp(self):
        self.auth = SimpleNamespace(msToken='test-ms-token', cookie={'ttwid': 'test'})
        self.response = Mock(
            text='{"status_code": 0}',
            headers={},
            json=Mock(return_value={'status_code': 0, 'data': {}}),
        )

    @patch('dy_apis.douyin_api.Params.with_a_bogus', fake_sign)
    @patch('dy_apis.douyin_api.requests.get')
    def test_contribution_rank_matches_current_web_request(self, mock_get):
        mock_get.return_value = self.response

        result = DouyinAPI.get_live_contribution_rank(
            self.auth,
            room_id='7684850982013930249',
            anchor_id='87376620793',
            sec_anchor_id='sec-anchor',
            web_rid='359765653648',
        )

        self.assertEqual(result['status_code'], 0)
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], 'https://live.douyin.com/webcast/ranklist/audience/')
        self.assertEqual(kwargs['headers']['referer'],
                         'https://live.douyin.com/359765653648')
        self.assertEqual(kwargs['params']['rank_type'], '30')
        self.assertEqual(kwargs['params']['ignoreToast'], 'true')
        self.assertEqual(kwargs['params']['os_name'], 'Windows')
        self.assertEqual(kwargs['params']['a_bogus'],
                         'signed-for:live.douyin.com')
        self.assertNotIn('update_scene', kwargs['params'])

    @patch('dy_apis.douyin_api.Params.with_a_bogus', fake_sign)
    @patch('dy_apis.douyin_api.requests.get')
    def test_thousand_ticket_rank_uses_paygrade_seats(self, mock_get):
        self.auth.request = Mock(return_value=self.response)

        DouyinAPI.get_live_thousand_ticket_rank(
            self.auth,
            room_id='7684850982013930249',
            web_rid='359765653648',
        )

        mock_get.assert_not_called()
        args, kwargs = self.auth.request.call_args
        self.assertEqual(args[0], 'GET')
        self.assertEqual(
            args[1],
            'https://live.douyin.com/webcast/ranklist/paygrade_seats/',
        )
        self.assertEqual(kwargs['params']['seats_type'], '2')
        self.assertNotIn('anchor_id', kwargs['params'])
        self.assertNotIn('sec_anchor_id', kwargs['params'])

    @patch.object(DouyinAPI, 'get_live_contribution_rank')
    def test_old_rank_list_name_is_kept_as_alias(self, contribution_rank):
        contribution_rank.return_value = {'status_code': 0}

        result = DouyinAPI.get_rank_list(
            self.auth, 'room', 'anchor', 'sec-anchor', web_rid='web-rid'
        )

        self.assertEqual(result['status_code'], 0)
        contribution_rank.assert_called_once_with(
            self.auth, 'room', 'anchor', 'sec-anchor', web_rid='web-rid'
        )


if __name__ == '__main__':
    unittest.main()
