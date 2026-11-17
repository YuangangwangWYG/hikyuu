#!/usr/bin/python
# -*- coding: utf-8 -*-
# cp936

# ===============================================================================
# A batch backtest over a stock pool (the CSI 300 constituents by default).
#
# Buy signal : the weekly MACD golden cross below the zero axis
# Sell signal: the daily close falls below the 20-day moving average
#
# Usage:
#   python run_batch_backtest.py [pool] [start] [end]
#     pool  : hs300 (default) | hsy300 | top | all
#     start : the start date, e.g. 2015-01-01
#     end   : the end date, e.g. 2026-11-01
# ===============================================================================

import os
import sys
from datetime import timedelta

# the hikyuu package is used from the repository source tree (it is not pip-installed),
# so the repository root must be on sys.path before importing it
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hikyuu import *


def getNextWeekDate(week):
    """Get the date of the next Monday after the given date"""
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

    # the daily sell signal
    day_c = CLOSE(k)
    day_ma = MA(day_c, self.get_param("day_n"))
    day_x = day_c < day_ma
    for i in range(day_x.discard, len(day_x)):
        if day_x[i] >= 1.0:
            self._add_sell_signal(k[i].datetime)

    # the weekly buy signal
    week_k = k.get_kdata(Query.WEEK)
    if len(week_k) == 0:
        return
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
    """Buy: all the cash; Sell: the whole position"""

    def __init__(self):
        super(DEMO_MM, self).__init__("MACD_MM")

    def _reset(self):
        pass

    def _clone(self):
        return DEMO_MM()

    def _get_buy_num(self, datetime, stk, price, risk, part_from):
        return self.tm.current_cash / price

    def _get_sell_num(self, datetime, stk, price, risk, part_from):
        total_num = self.tm.get_position(datetime, stk).number
        return total_num if total_num >= 100 else 0


def load_pool(pool, sm):
    """Get the stock list of the given pool"""
    if pool == 'hs300':
        tsv = os.path.expanduser('~') + '/CodeBuddy/hikyuu-project/data/hs300_cons.tsv'
        codes = []
        with open(tsv) as f:
            for line in f:
                p = line.strip().split('\t')
                if len(p) >= 3 and p[0]:
                    codes.append(p[2] + p[0])
        return [get_stock(c) for c in codes]

    if pool == 'top':
        # the stocks with the most K-line bars
        stocks = []
        for s in sm:
            if s.type == 1:  # the A-share stock
                stocks.append(s)
        stocks.sort(key=lambda s: len(s.get_kdata(Query(0, 0))), reverse=True)
        return stocks[:50]

    if pool == 'all':
        return [s for s in sm if s.type == 1]

    raise ValueError("unknown pool: {}".format(pool))


def run_one(stk, start_date, end_date, init_cash):
    """Run the backtest of a single stock and return the result dict"""
    my_tm = crtTM(date=Datetime('1990-1-1'), init_cash=init_cash, cost_func=TC_FixedA())
    my_sys = SYS_Simple()
    my_sys.tm = my_tm
    my_sys.sg = crtSG(DEMO_SG,
                      {'week_macd_n1': 12, 'week_macd_n2': 26, 'week_macd_n3': 9, 'day_n': 20},
                      'DEMO_SG')
    my_sys.sg.set_param('alternate', False)
    my_sys.mm = DEMO_MM()

    q = Query(start_date, end_date, ktype=Query.DAY)
    my_sys.run(stk, q)

    per = my_tm.get_performance()
    per.statistics(my_tm, Datetime.now())

    # the equity curve and the close price, both on the stock's own trading date axis
    k = stk.get_kdata(q)
    dts = stk.get_datetime_list(q)

    return {
        'code': stk.market_code,
        'name': stk.name,
        'total': per['Current Total Assets'],
        'ret': per['Closed Trade Account Return %'],
        'annual': per['Account CAGR %'],
        'trade_cnt': int(per['Total Closed Trades']),
        'win_cnt': int(per['Number of Winning Trades']),
        'loss_cnt': int(per['Number of Losing Trades']),
        'win_ratio': per['Win Rate %'],
        'profit': per['Total Net Profit of Closed Trades'],
        'cost': per['Total Cost of Closed Trades'],
        'profit_factor': per['Profit Factor'],
        'dates': list(dts),
        'curve': list(my_tm.get_profit_curve(dts, Query.DAY)),
        'close': [rec.close for rec in k],
    }


def align_to_axis(values, dates, axis):
    """Align a value series onto the common date axis by forward filling (the last known
    value is carried forward); before the first date the value is 0.0"""
    out = []
    j = 0
    n = len(dates)
    for d in axis:
        while j < n and dates[j] <= d:
            j += 1
        out.append(values[j - 1] if j > 0 else 0.0)
    return out


if __name__ == "__main__":
    pool = sys.argv[1] if len(sys.argv) > 1 else 'hs300'
    start_date = Datetime(sys.argv[2]) if len(sys.argv) > 2 else Datetime('2015-01-01')
    end_date = Datetime(sys.argv[3]) if len(sys.argv) > 3 else Datetime('2026-11-01')
    init_cash = 100000

    hikyuu_init(os.path.expanduser('~') + "/.hikyuu/hikyuu.ini")
    sm = StockManager.instance()

    stocks = load_pool(pool, sm)
    print("=" * 90)
    print("Batch backtest | pool={} | stocks={} | {} ~ {} | init_cash={}".format(
        pool, len(stocks), start_date, end_date, init_cash))
    print("=" * 90)

    results = []
    for i, stk in enumerate(stocks):
        try:
            res = run_one(stk, start_date, end_date, init_cash)
            results.append(res)
        except Exception as e:
            print("  [skip] {} {}: {}".format(stk.market_code, stk.name, e))
            continue
        if (i + 1) % 50 == 0:
            print("  ... {} / {} done".format(i + 1, len(stocks)))

    print()
    print("=" * 90)
    print("Results ({} stocks)".format(len(results)))
    print("=" * 90)
    print("{:<10} {:<10} {:>12} {:>10} {:>8} {:>8} {:>10} {:>8}".format(
        'code', 'name', 'total', 'ret%', 'annual%', 'trades', 'win%', 'profit'))
    for r in sorted(results, key=lambda x: x['ret'], reverse=True):
        print("{:<10} {:<10} {:>12.2f} {:>10.2f} {:>8.2f} {:>8} {:>10.2f} {:>8.0f}".format(
            r['code'], r['name'], r['total'], r['ret'], r['annual'],
            r['trade_cnt'], r['win_ratio'], r['profit']))

    # the summary
    if results:
        rets = sorted(r['ret'] for r in results)
        anns = sorted(r['annual'] for r in results)
        n = len(rets)
        total_trades = sum(r['trade_cnt'] for r in results)
        win_trades = sum(r['win_cnt'] for r in results)
        loss_trades = sum(r['loss_cnt'] for r in results)
        profit_stocks = len([r for r in results if r['ret'] > 0])

        print()
        print("=" * 90)
        print("Summary")
        print("=" * 90)
        print("  stocks with data        : {}".format(n))
        print("  profitable stocks       : {} ({:.1f}%)".format(
            profit_stocks, profit_stocks * 100.0 / n))
        print("  median return %         : {:.2f}".format(rets[n // 2]))
        print("  mean return %           : {:.2f}".format(sum(rets) / n))
        print("  best / worst return %   : {:.2f} / {:.2f}".format(rets[-1], rets[0]))
        print("  median annual %         : {:.2f}".format(anns[n // 2]))
        print("  best / worst annual %   : {:.2f} / {:.2f}".format(anns[-1], anns[0]))
        print("  total closed trades     : {}".format(total_trades))
        print("  win / loss trades       : {} / {}".format(win_trades, loss_trades))
        print("  overall win ratio %     : {:.2f}".format(
            win_trades * 100.0 / total_trades if total_trades else 0))

        # the equal-weight portfolio: the average of the per-stock equity curves, all aligned
        # onto the common trading-date axis of the whole pool
        # (the axis is the union of the trading dates of the pool; the stock manager's trading
        #  calendar is not usable here because the local data has no index record)
        date_set = set()
        for r in results:
            date_set.update(r['dates'])
        axis = sorted(date_set)
        if axis and results:
            length = len(axis)
            aligned = []
            for r in results:
                if not r['dates']:
                    continue
                aligned.append(align_to_axis(r['curve'], r['dates'], axis))
            if aligned:
                port = [sum(c[i] for c in aligned) / len(aligned) for i in range(length)]

                # the benchmark: the equal-weight buy-and-hold of the same stocks
                bench = [0.0] * length
                bench_cnt = 0
                for r in results:
                    if not r['close'] or not r['dates']:
                        continue
                    first = r['close'][0]
                    if not first:
                        continue
                    bench_cnt += 1
                    ret = [c / first - 1.0 for c in r['close']]
                    aligned_ret = align_to_axis(ret, r['dates'], axis)
                    for i in range(length):
                        bench[i] += aligned_ret[i] * init_cash / len(results)
                if bench_cnt:
                    bench = [v * len(results) / bench_cnt for v in bench]

                # the metrics are computed on the net asset value curve (init_cash + profit)
                def metrics(curve):
                    nav = [init_cash + v for v in curve]
                    peak = nav[0]
                    max_dd = 0.0
                    for v in nav:
                        peak = max(peak, v)
                        if peak:
                            max_dd = min(max_dd, (v - peak) / peak * 100)
                    total = nav[-1]
                    ret = (total / init_cash - 1) * 100
                    years = (end_date - start_date).days / 365.0
                    annual = ((total / init_cash) ** (1 / years) - 1) * 100 if years > 0 else 0
                    return total, ret, annual, max_dd

                port_total, port_ret, port_annual, port_dd = metrics(port)
                bench_total, bench_ret, bench_annual, bench_dd = metrics(bench)

                print()
                print("=" * 90)
                print("Equal-weight portfolio ({} stocks, {} trading days)".format(
                    len(aligned), length))
                print("=" * 90)
                print("  final total assets      : {:.2f}".format(port_total))
                print("  cumulative return %     : {:.2f}".format(port_ret))
                print("  annualized return %     : {:.2f}".format(port_annual))
                print("  max drawdown %          : {:.2f}".format(port_dd))
                print("  benchmark (buy & hold)  : {:.2f} ({:.2f}%, annual {:.2f}%, dd {:.2f}%)".format(
                    bench_total, bench_ret, bench_annual, bench_dd))

                # the chart: the distribution + the portfolio curve
                import matplotlib
                matplotlib.use('Agg')
                import matplotlib.pyplot as plt
                import matplotlib.dates as mdates

                fig = plt.figure(figsize=(16, 9))
                gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1])

                ax1 = fig.add_subplot(gs[0, :])
                x = [d.datetime() for d in axis]
                ax1.plot(x, [init_cash + v for v in port], linewidth=1.4, color='#4C78A8',
                         label='strategy (equal weight)')
                ax1.plot(x, [init_cash + v for v in bench], linewidth=1.4, color='#BAB0AC',
                         linestyle='--', label='benchmark (buy & hold)')
                ax1.axhline(init_cash, color='#999999', linewidth=0.8)
                ax1.set_title('Equal-weight portfolio net asset value | {} | {} ~ {}'.format(
                    pool, start_date, end_date))
                ax1.set_ylabel('total assets')
                ax1.legend(loc='upper left')
                ax1.grid(True, alpha=0.3)
                ax1.xaxis.set_major_locator(mdates.YearLocator())
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
                fig.autofmt_xdate(rotation=0)

                ax2 = fig.add_subplot(gs[1, 0])
                ax2.hist(rets, bins=30, color='#4C78A8', edgecolor='white', linewidth=0.6)
                ax2.axvline(0, color='#E45756', linewidth=1.5, linestyle='--')
                ax2.axvline(rets[n // 2], color='#54A24B', linewidth=1.5, linestyle=':')
                ax2.set_title('Return distribution ({} stocks)'.format(n))
                ax2.set_xlabel('closed return %')
                ax2.set_ylabel('stock count')
                ax2.grid(True, alpha=0.3)

                ax3 = fig.add_subplot(gs[1, 1])
                ax3.hist(anns, bins=30, color='#F58518', edgecolor='white', linewidth=0.6)
                ax3.axvline(0, color='#E45756', linewidth=1.5, linestyle='--')
                ax3.axvline(anns[n // 2], color='#54A24B', linewidth=1.5, linestyle=':')
                ax3.set_title('Annualized return distribution')
                ax3.set_xlabel('annualized return %')
                ax3.set_ylabel('stock count')
                ax3.grid(True, alpha=0.3)

                fig.tight_layout()
                out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'batch_backtest_{}.png'.format(pool))
                fig.savefig(out, dpi=110)

        # the csv of the details
        import csv
        csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'batch_backtest_{}.csv'.format(pool))
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['code', 'name', 'total', 'ret%', 'annual%', 'trade_cnt',
                             'win_cnt', 'loss_cnt', 'win_ratio%', 'profit', 'cost', 'profit_factor'])
            for r in sorted(results, key=lambda x: x['ret'], reverse=True):
                writer.writerow([r['code'], r['name'], '{:.2f}'.format(r['total']),
                                 '{:.2f}'.format(r['ret']), '{:.2f}'.format(r['annual']),
                                 r['trade_cnt'], r['win_cnt'], r['loss_cnt'],
                                 '{:.2f}'.format(r['win_ratio']), '{:.2f}'.format(r['profit']),
                                 '{:.2f}'.format(r['cost']), '{:.3f}'.format(r['profit_factor'])])

        print()
        print("  the distribution chart : {}".format(out))
        print("  the details csv        : {}".format(csv_path))
