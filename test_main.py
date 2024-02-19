import json
import unittest
from unittest.mock import patch, AsyncMock
import websockets

from main import DeribitClient


class TestDeribitClient(unittest.TestCase):
    def setUp(self):
        self.url = "wss://test.deribit.com/ws/api/v2"
        self.symbol = "BTC-PERPETUAL"
        self.client = DeribitClient(self.url, self.symbol)

    @patch('websockets.connect', new_callable=AsyncMock)
    def test_init(self, mock_websockets):
        self.assertEqual(self.client.url, self.url)
        self.assertEqual(self.client.symbol, self.symbol)
        self.assertIsNone(self.client.websocket)
        self.assertIsNone(self.client.current_orderbook)
        self.assertIsNone(self.client.book_subscribe)
        self.assertIsNone(self.client.trades_subscribe)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_websocket_manager(self, mock_connect):
        mock_connect.return_value = AsyncMock()
        self.client.set_heartbeat = AsyncMock()
        self.client.get_orderbook_data = AsyncMock()
        self.client.subscribe = AsyncMock()
        self.client.handle_messages = AsyncMock()

        await self.client.websocket_manager()

        mock_connect.assert_called_with(self.url)
        self.client.set_heartbeat.assert_awaited()
        self.client.get_orderbook_data.assert_awaited()
        self.client.subscribe.assert_awaited()
        self.client.handle_messages.assert_awaited()

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_set_heartbeat(self, mock_connect):
        self.client.websocket = mock_connect
        await self.client.set_heartbeat()

        expected_msg = json.dumps({
            "jsonrpc": "2.0",
            "id": 9098,
            "method": "public/set_heartbeat",
            "params": {"interval": 10}
        })
        self.client.websocket.send.assert_awaited_with(expected_msg)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_subscribe(self, mock_connect):
        self.client.websocket = mock_connect
        ws_channel = f'book.{self.symbol}.100ms'
        await self.client.subscribe(ws_channel)

        expected_msg = json.dumps({
            "jsonrpc": "2.0",
            "method": "public/subscribe",
            "id": 42,
            "params": {"channels": [ws_channel]}
        })
        self.client.websocket.send.assert_awaited_with(expected_msg)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_connection_failure_and_retry(self, mock_connect):
        mock_connect.side_effect = [Exception("Connection failed"), AsyncMock()]

        with self.assertLogs(level='INFO') as log:
            await self.client.websocket_manager()
            self.assertIn("Attempting to reconnect...", log.output)

        self.assertEqual(mock_connect.call_count, 2)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_handle_malformed_json_message(self, mock_connect):
        websocket_mock = mock_connect.return_value
        websocket_mock.recv = AsyncMock(side_effect=["{malformed json"])

        with self.assertLogs(level='ERROR') as log:
            await self.client.handle_messages()
            self.assertIn("Error parsing JSON message", log.output)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_unexpected_message_type(self, mock_connect):
        unexpected_message = json.dumps({"jsonrpc": "2.0", "method": "unexpected_method"})
        websocket_mock = mock_connect.return_value
        websocket_mock.recv = AsyncMock(return_value=unexpected_message)

        with self.assertLogs(level='WARNING') as log:
            await self.client.handle_messages()
            self.assertIn("Warning: Unhandled method: unexpected_method", log.output)

    @patch('websockets.connect')
    async def test_websocket_reconnects_after_interruption(self, mock_connect):
        # Simulating a disconnection
        first_connection_mock = AsyncMock()
        first_connection_mock.recv = AsyncMock(
            side_effect=websockets.ConnectionClosed(1000, "Normal Closure"))

        second_connection_mock = AsyncMock()
        second_connection_mock.recv = AsyncMock(return_value='{"jsonrpc": "2.0", "result": {}}')

        mock_connect.side_effect = [first_connection_mock, second_connection_mock]

        await self.client.websocket_manager()
        self.assertEqual(mock_connect.call_count, 2)

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_handle_orderbook_update(self, mock_connect):
        message = json.dumps({
            "jsonrpc": "2.0",
            "method": "subscription",
            "params": {
                "channel": f"book.{self.symbol}.100ms",
                "data": {"action": "update",
                         "data": {"best_ask_price": 10000, "best_bid_price": 9990}}
            }
        })
        mock_connect.return_value.recv = AsyncMock(return_value=message)

        self.client.process_orderbook_update = AsyncMock()
        await self.client.handle_messages()
        self.client.process_orderbook_update.assert_awaited()

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_handle_trade_update(self, mock_connect):
        message = json.dumps({
            "jsonrpc": "2.0",
            "method": "subscription",
            "params": {
                "channel": f"trades.{self.symbol}.100ms",
                "data": {"action": "new", "data": {"price": 10000, "amount": 1}}
            }
        })
        mock_connect.return_value.recv = AsyncMock(return_value=message)

        self.client.process_trade_update = AsyncMock()
        await self.client.handle_messages()
        self.client.process_trade_update.assert_awaited()

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_handle_heartbeat(self, mock_connect):
        message = json.dumps({"jsonrpc": "2.0", "method": "heartbeat"})
        mock_connect.return_value.recv = AsyncMock(return_value=message)

        self.client.heartbeat_response = AsyncMock()
        await self.client.handle_messages()
        self.client.heartbeat_response.assert_awaited()

    @patch('websockets.connect', new_callable=AsyncMock)
    async def test_handle_unknown_message(self, mock_connect):
        message = json.dumps({"jsonrpc": "2.0", "method": "unknown_method"})
        mock_connect.return_value.recv = AsyncMock(return_value=message)

        with self.assertLogs(level='WARNING') as log:
            await self.client.handle_messages()
            self.assertIn("Warning: Unhandled method: unknown_method", log.output)


if __name__ == '__main__':
    unittest.main()
