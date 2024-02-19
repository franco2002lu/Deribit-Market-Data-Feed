import asyncio
import websockets
import json
import sys
import logging


class DeribitClient:
    def __init__(self, url, symbol):
        self.url = url
        self.symbol = symbol
        self.websocket = websockets.WebSocketClientProtocol = None
        self.current_orderbook = None
        self.book_subscribe = None
        self.trades_subscribe = None
        self.book_id = None
        self.trade_id = None

    async def websocket_manager(self):
        while True:
            try:
                async with websockets.connect(self.url) as self.websocket:
                    await self.set_heartbeat()

                    await self.get_orderbook_data()

                    self.book_subscribe = await asyncio.create_task(
                        self.subscribe(
                            ws_channel=f'book.{self.symbol}.100ms'
                        )
                    )

                    self.trades_subscribe = await asyncio.create_task(
                        self.subscribe(
                            ws_channel=f'trades.{self.symbol}.100ms'
                        )
                    )

                    await self.handle_messages()

            except websockets.ConnectionClosed:
                print("Connection closed, attempting to reconnect...")
                await asyncio.sleep(0.5)

    async def set_heartbeat(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 9098,
            "method": "public/set_heartbeat",
            "params": {
                "interval": 10
            }
        }

        await self.websocket.send(json.dumps(msg))

    async def heartbeat_response(self) -> None:
        msg = {
            "jsonrpc": "2.0",
            "id": 8212,
            "method": "public/test",
            "params": {}
        }

        await self.websocket.send(json.dumps(msg))

    async def subscribe(self, ws_channel):
        await asyncio.sleep(0.5)

        msg = {
            "jsonrpc": "2.0",
            "method": "public/subscribe",
            "id": 42,
            "params": {
                "channels": [ws_channel]
            }
        }

        await self.websocket.send(json.dumps(msg))

        print(f'New subscription created: {ws_channel}')

    async def get_orderbook_data(self):
        msg = {
            "jsonrpc": "2.0",
            "id": 8772,
            "method": "public/get_order_book",
            "params": {
                "instrument_name": f"{self.symbol}",
                "depth": 5
            }
        }

        await self.websocket.send(json.dumps(msg))

    def display_book(self):
        asks = self.current_orderbook['asks']
        bids = self.current_orderbook['bids']
        for order in reversed(asks):
            print(f'{order[1]:.2f} @ {order[0]:.1f}')
        print(f'-----------------------------------------')
        for order in bids:
            print(f'{order[1]:.2f} @ {order[0]:.1f}')
        print('')

    def display_trade(self, data):
        for trade in data:
            price = trade['price']
            amount = trade['amount']
            print(f'SOLD {amount} @ {price}')
            print(
                f'{self.current_orderbook['best_bid_amount']:.2f} @ {self.current_orderbook['best_bid_price']:.1f}')
            print(f'-----------------------------------------')
            print(
                f'{self.current_orderbook['best_ask_amount']:.2f} @ {self.current_orderbook['best_ask_price']:.1f}')
            print('')

    async def check_book_order(self, data):
        # check for book event order, restart if necessary
        if 'prev_change_id' in data and data['prev_change_id'] != self.book_id:
            print('Error fetching orderbook data, restarting websocket connection.')

            self.book_subscribe.cancel()
            self.book_subscribe = await asyncio.create_task(
                self.subscribe(
                    ws_channel=f'book.{self.symbol}.100ms'
                )
            )
        else:
            self.book_id = data['change_id']

    async def check_trade_order(self, data):
        # check for trade event order, restart if necessary
        if 'trade_id' in data[0]:
            if self.trade_id and data[0]['trade_id'] <= self.trade_id:
                print('Error fetching trade data, restarting websocket connection.')

                self.trades_subscribe.cancel()
                self.trades_subscribe = await asyncio.create_task(
                    self.subscribe(
                        ws_channel=f'trades.{self.symbol}.100ms'
                    )
                )
            else:
                self.trade_id = data[0]['trade_id']

    async def handle_messages(self):
        while self.websocket.open:
            # receives message
            message = await self.websocket.recv()
            message = json.loads(message)

            # only certain events (subscription, heartbeat) have the 'method' parameter
            if 'method' in list(message):
                if message['method'] == 'subscription':
                    params = message['params']
                    channel = params['channel']
                    data = params['data']

                    # gets a updated version of orderbook everytime a relevant event is received
                    await self.get_orderbook_data()

                    # book event
                    if channel.startswith('book'):
                        await self.check_book_order(data)
                        self.display_book()

                    # trades event
                    elif channel.startswith('trades'):
                        await self.check_trade_order(data)
                        self.display_trade(data)

                # handles heartbeat events
                elif message['method'] == 'heartbeat':
                    await self.heartbeat_response()
                else:
                    print(f'Warning: Unhandled method: {message['method']}')
            else:
                # if we are receiving the result of the get_order_book request
                if message['id'] == 8772:
                    self.current_orderbook = message['result']

        else:
            logging.info('Websocket connection has been broken.')
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: need to provide a symbol as command line argument")
        sys.exit(1)

    instrument_name = sys.argv[1]
    api_url = "wss://www.deribit.com/ws/api/v2"

    client = DeribitClient(api_url, instrument_name)
    asyncio.run(client.websocket_manager())
