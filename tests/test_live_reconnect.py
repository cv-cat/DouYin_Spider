import unittest
from unittest.mock import Mock, patch

from dy_live.server import DouyinLive


class DouyinLiveReconnectTest(unittest.TestCase):
    def make_live(self):
        live = DouyinLive.__new__(DouyinLive)
        live.ws = None
        live.auto_reconnect = True
        live.max_reconnect_attempts = 3
        live.reconnect_base_delay = 1
        live.reconnect_max_delay = 2
        live._connection_closed = False
        live._stop_requested = False
        return live

    def test_run_return_after_user_interrupt_does_not_reconnect(self):
        live = self.make_live()
        live._run_websocket = Mock(return_value=False)

        with patch('dy_live.server.time.sleep') as sleep:
            live.start_ws()

        live._run_websocket.assert_called_once_with()
        sleep.assert_not_called()

    def test_connection_failures_use_bounded_backoff(self):
        live = self.make_live()
        live._run_websocket = Mock(side_effect=[True, True, True, True])

        with patch('dy_live.server.time.sleep') as sleep:
            live.start_ws()

        self.assertEqual(live._run_websocket.call_count, 4)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [1, 2, 2],
        )

    def test_setup_error_is_not_retried(self):
        live = self.make_live()
        live._run_websocket = Mock(side_effect=ValueError('invalid room'))

        with self.assertRaisesRegex(ValueError, 'invalid room'):
            live.start_ws()

        live._run_websocket.assert_called_once_with()

    def test_keyboard_interrupt_callback_requests_stop(self):
        live = self.make_live()

        with patch('builtins.print'):
            live.on_error(None, KeyboardInterrupt())
            live.on_close(None, None, None)

        self.assertTrue(live._stop_requested)
        self.assertTrue(live._connection_closed)
        self.assertFalse(live._should_reconnect(False))

    def test_remote_close_requests_reconnect(self):
        live = self.make_live()

        with patch('builtins.print'):
            live.on_close(None, 1000, 'closed')

        self.assertTrue(live._should_reconnect(False))


if __name__ == '__main__':
    unittest.main()
