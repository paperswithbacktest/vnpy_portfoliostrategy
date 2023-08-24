from typing import List, Dict
from datetime import datetime

from vnpy.trader.utility import BarGenerator, extract_vt_symbol
from vnpy.trader.object import TickData, BarData
from vnpy.trader.constant import Direction

from vnpy_portfoliostrategy import StrategyTemplate, StrategyEngine


class PcpArbitrageStrategy(StrategyTemplate):
    """Option Parity Arbitrage Strategy"""

    author = "Trader in Python."

    entry_level = 20
    price_add = 5
    fixed_size = 1

    strike_price = 0
    futures_price = 0
    synthetic_price = 0
    current_spread = 0
    futures_pos = 0
    call_pos = 0
    put_pos = 0
    futures_target = 0
    call_target = 0
    put_target = 0

    parameters = ["entry_level", "price_add", "fixed_size"]
    variables = [
        "strike_price",
        "futures_price",
        "synthetic_price",
        "current_spread",
        "futures_pos",
        "call_pos",
        "put_pos",
        "futures_target",
        "call_target",
        "put_target",
    ]

    def __init__(
        self,
        strategy_engine: StrategyEngine,
        strategy_name: str,
        vt_symbols: List[str],
        setting: dict,
    ) -> None:
        """Constructor"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        self.bgs: Dict[str, BarGenerator] = {}
        self.last_tick_time: datetime = None

        # 绑定合约代码
        for vt_symbol in self.vt_symbols:
            symbol, _ = extract_vt_symbol(vt_symbol)

            if "C" in symbol:
                self.call_symbol = vt_symbol
                _, strike_str = symbol.split("-C-")  # CFFEX/DCE
                self.strike_price = int(strike_str)
            elif "P" in symbol:
                self.put_symbol = vt_symbol
            else:
                self.futures_symbol = vt_symbol

            def on_bar(bar: BarData):
                """"""
                pass

            self.bgs[vt_symbol] = BarGenerator(on_bar)

    def on_init(self) -> None:
        """Strategy initialization callback""""
        self.write_log("Strategy initialized")

        self.load_bars(1)

    def on_start(self) -> None:
        """Strategy startup callback"""
        self.write_log("Strategy activated")

    def on_stop(self) -> None:
        """Strategy stop callback"""
        self.write_log("Strategy stopped")

    def on_tick(self, tick: TickData):
        """Strategy tick callback"""
        if self.last_tick_time and self.last_tick_time.minute != tick.datetime.minute:
            bars = {}
            for vt_symbol, bg in self.bgs.items():
                bars[vt_symbol] = bg.generate()
            self.on_bars(bars)

        bg: BarGenerator = self.bgs[tick.vt_symbol]
        bg.update_tick(tick)

        self.last_tick_time = tick.datetime

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        """Bar callback"""
        self.cancel_all()

        # Calculating the PCP Spread
        call_bar = bars[self.call_symbol]
        put_bar = bars[self.put_symbol]
        futures_bar = bars[self.futures_symbol]

        self.futures_price = futures_bar.close_price
        self.synthetic_price = (
            call_bar.close_price - put_bar.close_price + self.strike_price
        )
        self.current_spread = self.synthetic_price - self.futures_price

        # Calculate target position
        futures_target: int = self.get_target(self.futures_symbol)

        if not futures_target:
            if self.current_spread > self.entry_level:
                self.set_target(self.call_symbol, -self.fixed_size)
                self.set_target(self.put_symbol, self.fixed_size)
                self.set_target(self.futures_symbol, self.fixed_size)
            elif self.current_spread < -self.entry_level:
                self.set_target(self.call_symbol, self.fixed_size)
                self.set_target(self.put_symbol, -self.fixed_size)
                self.set_target(self.futures_symbol, -self.fixed_size)
        elif futures_target > 0:
            if self.current_spread <= 0:
                self.set_target(self.call_symbol, 0)
                self.set_target(self.put_symbol, 0)
                self.set_target(self.futures_symbol, 0)
        else:
            if self.current_spread >= 0:
                self.set_target(self.call_symbol, 0)
                self.set_target(self.put_symbol, 0)
                self.set_target(self.futures_symbol, 0)

        # Execution of position transfer transactions
        self.rebalance_portfolio()

        # Update strategy status
        self.call_pos = self.get_pos(self.call_symbol)
        self.put_pos = self.get_pos(self.put_symbol)
        self.futures_pos = self.get_pos(self.futures_symbol)

        self.call_target = self.get_target(self.call_symbol)
        self.put_target = self.get_target(self.put_symbol)
        self.futures_target = self.get_target(self.futures_symbol)

        self.put_event()

    def calculate_price(
        self, vt_symbol: str, direction: Direction, reference: float
    ) -> float:
        """Calculation of transfer commission price (supports on-demand reloading implementation)"""
        if direction == Direction.LONG:
            price: float = reference + self.price_add
        else:
            price: float = reference - self.price_add

        return price
