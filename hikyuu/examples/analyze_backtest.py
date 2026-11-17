#!/usr/bin/python
# -*- coding: utf-8 -*-
"""Diagnose why the MACD strategy lost money: benchmark + round-trip P&L."""

import os
import sys

# the hikyuu package is used from the repository source tree (it is not pip-installed),
# so the repository root must be on sys.path before importing it
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from hikyuu import *

hikyuu_init(os.path.expanduser('~') + '/.hikyuu/hikyuu.ini')

stk = get_stock('sh600000')
start = Datetime('2005-01-01')
end = Datetime('2026-11-01')
q = Query(start, end, ktype=Query.DAY)
k = stk.get_kdata(q)

print("=" * 72)
print("1) PRICE SERIES CHECK (adjustment / data quality)")
print("=" * 72)
print("bars:", len(k))
for i in [0, 250, 500, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000, len(k) - 1]:
    if 0 <= i < len(k):
        r = k[i]
        print("  {}  O={:.3f} H={:.3f} L={:.3f} C={:.3f}".format(
            r.datetime, r.open, r.high, r.low, r.close))

# biggest overnight gaps -> a sign of unadjusted dividends/splits
gaps = []
for i in range(1, len(k)):
    if k[i - 1].close > 0:
        g = (k[i].open - k[i - 1].close) / k[i - 1].close
        if abs(g) > 0.06:
            gaps.append((abs(g), k[i].datetime, g))
gaps.sort(reverse=True)
print("\n  overnight gaps > 6% (unadjusted dividend/split signs):", len(gaps))
for g in gaps[:8]:
    print("    {}  gap={:+.2%}".format(g[1], g[2]))

print()
print("=" * 72)
print("2) BUY & HOLD BENCHMARK (same window, same cost model)")
print("=" * 72)
first_close = k[0].close
last_close = k[-1].close
init_cash = 100000.0
cost = TC_FixedA()
buy_num = int(init_cash / first_close)
buy_cost = cost.get_buy_cost(start, stk, first_close, buy_num).total
cash_left = init_cash - buy_num * first_close - buy_cost
final_value = cash_left + buy_num * last_close
print("  buy @ {:.3f}  num={}  cost={:.2f}".format(first_close, buy_num, buy_cost))
print("  sell @ {:.3f} (last bar)".format(last_close))
print("  final assets: {:.2f}   total return: {:+.2%}".format(final_value, final_value / init_cash - 1))
years = (k[-1].datetime - k[0].datetime).days / 365.25
print("  years: {:.1f}   annualized: {:+.2%}".format(years, (final_value / init_cash) ** (1 / years) - 1))

print()
print("=" * 72)
print("3) THE STRATEGY'S SIGNAL QUALITY (forward return after each buy signal)")
print("=" * 72)
macd_w = MACD(CLOSE(k.get_kdata(Query.WEEK)), 12, 26, 9)
diff_w = macd_w.get_result(1)
dea_w = macd_w.get_result(2)
cross_w = CROSS(diff_w, dea_w)
wk = k.get_kdata(Query.WEEK)

ma20 = MA(CLOSE(k), 20)
closes = list(CLOSE(k))

fwd_buy = []
for i in range(cross_w.discard, len(cross_w)):
    if cross_w[i] >= 1.0 and diff_w[i] < 0:
        # the next Monday
        from datetime import timedelta
        pw = wk[i].datetime.datetime()
        nd = Datetime(pw + timedelta(days=7 - pw.weekday()))
        pos = k.get_pos(nd)
        if not pos:
            continue
        px = closes[pos]
        # forward 20 / 60 trading days
        r20 = (closes[min(pos + 20, len(closes) - 1)] / px - 1) if pos + 20 < len(closes) else None
        r60 = (closes[min(pos + 60, len(closes) - 1)] / px - 1) if pos + 60 < len(closes) else None
        fwd_buy.append((nd, px, r20, r60))

print("  valid buy signals:", len(fwd_buy))
r20s = [x[2] for x in fwd_buy if x[2] is not None]
r60s = [x[3] for x in fwd_buy if x[3] is not None]
if r20s:
    print("  forward 20d return: mean {:+.2%}  win-rate {:.1%}  median {:+.2%}".format(
        sum(r20s) / len(r20s), sum(1 for r in r20s if r > 0) / len(r20s),
        sorted(r20s)[len(r20s) // 2]))
if r60s:
    print("  forward 60d return: mean {:+.2%}  win-rate {:.1%}  median {:+.2%}".format(
        sum(r60s) / len(r60s), sum(1 for r in r60s if r > 0) / len(r60s),
        sorted(r60s)[len(r60s) // 2]))
print()
print("  the first 10 buy signals:")
for nd, px, r20, r60 in fwd_buy[:10]:
    print("    {}  px={:.3f}  fwd20={}  fwd60={}".format(
        nd, px,
        "{:+.2%}".format(r20) if r20 is not None else "n/a",
        "{:+.2%}".format(r60) if r60 is not None else "n/a"))

print()
print("=" * 72)
print("4) THE SELL CONDITION (close below MA20) FREQUENCY")
print("=" * 72)
below = sum(1 for i in range(ma20.discard, len(ma20)) if closes[i] < ma20[i])
print("  bars below MA20: {} / {}  ({:.1%} of the time)".format(
    below, len(closes) - ma20.discard, below / (len(closes) - ma20.discard)))
