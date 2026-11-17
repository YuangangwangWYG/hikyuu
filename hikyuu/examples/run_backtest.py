#!/usr/bin/python
# -*- coding: utf-8 -*-
# cp936

# ===============================================================================
# A runnable backtest demo, adapted from hikyuu/examples/notebook/zh/Demo/Demo1.ipynb
#
# Buy signal : the weekly MACD golden cross below the zero axis
# Sell signal: the daily close falls below the 20-day moving average
# ===============================================================================

import os
import sys

# the hikyuu package is used from the repository source tree (it is not pip-installed),
# so the repository root must be on sys.path before importing it
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hikyuu import *


def getNextWeekDate(week):
    """Get the date of the next Monday after the given date"""
    from datetime import timedelta
    py_week = week.datetime()
    next_week_start = py_week + timedelta(days=7 - py_week.weekday())
    return Datetime(next_week_start)


def DEMO_SG(self, k):
    """
    Buy signal: the weekly MACD golden cross below the zero axis
    Sell signal: the daily level falls below the 20-day moving average
    """
    if len(k) == 0:
        return

    # -------------------------
    # the daily sell signal
    # -------------------------
    day_c = CLOSE(k)
    day_ma = MA(day_c, self.get_param("day_n"))
    day_x = day_c < day_ma
    for i in range(day_x.discard, len(day_x)):
        if day_x[i] >= 1.0:
            self._add_sell_signal(k[i].datetime)

    # -------------------------
    # the weekly buy signal
    # -------------------------
    week_k = k.get_kdata(Query.WEEK)
    week_macd = MACD(CLOSE(week_k),
                     self.get_param("week_macd_n1"),
                     self.get_param("week_macd_n2"),
                     self.get_param("week_macd_n3"))
    # MACD is a multi-result indicator: 0=BAR(histogram), 1=DIFF(fast line), 2=DEA(slow line)
    week_diff = week_macd.get_result(1)
    week_dea = week_macd.get_result(2)
    week_x = CROSS(week_diff, week_dea)
    for i in range(week_x.discard, len(week_x)):
        if week_x[i] >= 1.0 and week_diff[i] < 0:
            d = getNextWeekDate(week_k[i].datetime)
            # the next Monday must be a trading day of the daily K-line
            if k.get_pos(d) == 0:
                continue
            self._add_buy_signal(d)


class DEMO_MM(MoneyManagerBase):
    """Buy: 30% of the current cash; Sell: 50% of the held shares"""

    def __init__(self):
        super(DEMO_MM, self).__init__("MACD_MM")

    def _reset(self):
        pass

    def _clone(self):
        return DEMO_MM()

    def _get_buy_num(self, datetime, stk, price, risk, part_from):
        cash = self.tm.current_cash
        return cash / price

    def _get_sell_num(self, datetime, stk, price, risk, part_from):
        # sell the whole position, so that the trades can be closed and settled
        total_num = self.tm.get_position(datetime, stk).number
        return total_num if total_num >= 100 else 0


if __name__ == "__main__":
    # usage: python run_backtest.py [code] [start] [end] [init_cash]
    #   code : the stock code, e.g. sh600000 (default: sh600000)
    #   start / end : the date range, e.g. 2005-01-01 (defaults: 2005-01-01 ~ today)
    #   init_cash : the initial capital (default: 100000)
    code = sys.argv[1] if len(sys.argv) > 1 else 'sh600000'
    start_date = Datetime(sys.argv[2]) if len(sys.argv) > 2 else Datetime('2005-01-01')
    end_date = Datetime(sys.argv[3]) if len(sys.argv) > 3 else Datetime.now()
    init_cash = float(sys.argv[4]) if len(sys.argv) > 4 else 100000

    config_file = os.path.expanduser('~') + "/.hikyuu/hikyuu.ini"
    hikyuu_init(config_file)
    sm = StockManager.instance()

    stk = get_stock(code)
    if stk is None or stk.is_null():
        print("Unknown stock code: {}".format(code))
        sys.exit(1)

    # the account
    init_date = Datetime('1990-1-1')
    my_tm = crtTM(date=init_date, init_cash=init_cash, cost_func=TC_FixedA())

    # the system
    my_sys = SYS_Simple()
    my_sys.tm = my_tm
    my_sys.sg = crtSG(DEMO_SG,
                      {'week_macd_n1': 12, 'week_macd_n2': 26, 'week_macd_n3': 9, 'day_n': 20},
                      'DEMO_SG')
    my_sys.sg.set_param('alternate', False)
    my_sys.mm = DEMO_MM()

    q = Query(start_date, end_date, ktype=Query.DAY)

    print("=" * 70)
    print("Backtesting {} ({}) from {} to {}".format(stk.name, stk.market_code, start_date, end_date))
    print("=" * 70)

    my_sys.run(stk, q)

    per = my_tm.get_performance()
    per.statistics(my_tm, Datetime.now())
    print(per.report())

    trade_list = my_tm.get_trade_list()
    pos_list = my_tm.get_position_list()

    print("=" * 70)
    print("Trade records ({} in total)".format(len(trade_list)))
    print("=" * 70)
    for tr in trade_list:
        print("  {} {:<13} {:<10} num={:<9} price={:<7.3f} cost={}".format(
            tr.datetime, str(tr.business).replace('BUSINESS.', ''), tr.stock.market_code,
            tr.number, tr.real_price, tr.cost.total))

    print()
    print("=" * 70)
    print("Position records ({} in total)".format(len(pos_list)))
    print("=" * 70)
    for pr in pos_list:
        print("  {}  take={}  buy={} sell={}  total_profit={}".format(
            pr.stock.market_code, pr.take_datetime, pr.buy_count, pr.sell_count, pr.total_profit))

    # the equity curve, saved as a png file
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    dts = stk.get_datetime_list(q)
    curve = list(my_tm.get_profit_curve(dts, Query.DAY))
    x = [d.datetime() for d in dts]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(x, curve, linewidth=1.2)
    ax.set_title('{} ({}) equity curve, {} to {}'.format(
        stk.name, stk.market_code, start_date, end_date))
    ax.set_xlabel('date')
    ax.set_ylabel('cumulative profit')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    fig.autofmt_xdate()
    fig.tight_layout()
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'backtest_equity_curve_{}.png'.format(stk.market_code))
    fig.savefig(out, dpi=110)
    print()
    print("The equity curve has been saved to: {}".format(out))
