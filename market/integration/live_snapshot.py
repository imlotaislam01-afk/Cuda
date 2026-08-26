import asyncio

from brain.context.market_state import MarketState
from market.bybit.public_ws import BybitPublicFeed
from market.orderflow import OrderFlowEngine
from market.orderflow.rolling import RollingOrderFlow


class LiveMarketSnapshot:

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        stale_thresholds: dict[str, float] | None = None,
    ):

        self.symbol = symbol.upper()

        self.feed = BybitPublicFeed(
            symbol=self.symbol,
            orderbook_depth=50,
            stale_thresholds=stale_thresholds,
        )

        self.orderflow = OrderFlowEngine()

        self.rolling = RollingOrderFlow()

        self.processed_trade_ids: set[str] = set()

    def run_pipeline(
        self,
        pipeline=None,
        calculation_time: float | None = None,
        as_of: float | None = None,
    ):
        from brain.pipeline import ApexBrainPipeline
        from market.integration.context_adapter import LiveSnapshotContextAdapter

        context = LiveSnapshotContextAdapter(self).build(
            calculation_time=calculation_time,
            as_of=as_of,
        )
        if context is None:
            return None
        return (pipeline or ApexBrainPipeline()).run(context)

    def _process_new_trades(self):

        trades = self.feed.data.trades

        for trade in trades:

            trade_id = str(
                trade.get("id")
            )

            if not trade_id:
                continue

            if trade_id in self.processed_trade_ids:
                continue

            self.processed_trade_ids.add(
                trade_id
            )

            self.rolling.add_trade(
                timestamp=(
                    trade["timestamp"] / 1000
                ),
                side=trade["side"],
                quantity=trade["quantity"],
            )

        # Keep memory bounded.
        if len(
            self.processed_trade_ids
        ) > 10000:

            self.processed_trade_ids = set(
                list(
                    self.processed_trade_ids
                )[-5000:]
            )

    def build(self, calculation_time: float | None = None) -> MarketState | None:

        data = self.feed.data

        if data.price is None:
            return None

        self._process_new_trades()

        imbalance = (
            data.orderbook_imbalance(
                depth=20
            )
        )

        recent_trades = data.trades[-500:]

        flow = self.orderflow.analyze(
            trades=recent_trades,
            orderbook_imbalance=imbalance,
        )

        rolling = self.rolling.snapshot(as_of=data.last_event_time)
        quality, quality_reason = data.quality(now=calculation_time, thresholds=self.feed.stale_thresholds)

        return MarketState(

            symbol=self.symbol,

            timestamp=data.last_event_time or data.last_update,

            price=data.price,

            timeframe="realtime",

            order_flow={

                "buy_volume": flow.buy_volume,

                "sell_volume": flow.sell_volume,

                "delta": flow.delta,

                "cumulative_delta":
                    flow.cumulative_delta,

                "buy_sell_ratio":
                    flow.buy_sell_ratio,

                "bias": flow.bias,

                "aggression":
                    flow.aggression,

                "absorption":
                    flow.absorption,

                "trade_count": flow.trade_count,

                "buy_sell_imbalance": flow.buy_sell_imbalance,

                "rolling": {
                    str(window): vars(snapshot)
                    for window, snapshot
                    in rolling.items()
                },
            },

            orderbook={

                "imbalance": imbalance,

                "bid_levels":
                    len(data.bids),

                "ask_levels":
                    len(data.asks),

                "best_bid": (
                    data.sorted_bids(1)[0][0]
                    if data.sorted_bids(1)
                    else None
                ),

                "best_ask": (
                    data.sorted_asks(1)[0][0]
                    if data.sorted_asks(1)
                    else None
                ),

                "top_bids":
                    data.snapshot_bids(20),

                "top_asks":
                    data.snapshot_asks(20),
            },

            metadata={
                "data_quality": quality,
                "data_quality_reason": quality_reason,
                "event_time": data.last_event_time,
                "received_time": data.last_update,
            },
        )


async def main():

    snapshot = LiveMarketSnapshot(
        "BTCUSDT"
    )

    from brain.pipeline import ApexBrainPipeline

    pipeline = ApexBrainPipeline()

    feed_task = asyncio.create_task(
        snapshot.feed.run()
    )

    print()
    print(
        "======================================"
    )
    print(
        "        APEX LIVE MARKET FEED"
    )
    print(
        "======================================"
    )

    try:

        while True:

            result = snapshot.run_pipeline(pipeline)
            state = snapshot.build()

            if state and result:

                flow = state.order_flow

                print()
                print(
                    "========== LIVE SNAPSHOT =========="
                )

                print(
                    f"Symbol:       "
                    f"{state.symbol}"
                )

                print(
                    f"Price:        "
                    f"{state.price:.2f}"
                )

                print(
                    f"Delta:        "
                    f"{flow['delta']:+.4f}"
                )

                print(
                    f"CVD:          "
                    f"{flow['cumulative_delta']:+.4f}"
                )

                print(
                    f"Buy/Sell:     "
                    f"{flow['buy_sell_ratio']:.2f}"
                )

                print(
                    f"OB Imbalance: "
                    f"{state.orderbook['imbalance']:+.3f}"
                )

                print(
                    f"Bias:         "
                    f"{flow['bias']}"
                )

                print(
                    f"Aggression:   "
                    f"{flow['aggression']}"
                )

                print(
                    f"Absorption:   "
                    f"{flow['absorption']}"
                )

                print(
                    f"Book levels:  "
                    f"{state.orderbook['bid_levels']}/"
                    f"{state.orderbook['ask_levels']}"
                )

                print(
                    "=================================="
                )

            await asyncio.sleep(2)

    except KeyboardInterrupt:

        print()
        print(
            "Stopping APEX live feed..."
        )

    finally:

        snapshot.feed.stop()

        feed_task.cancel()

        try:
            await feed_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
