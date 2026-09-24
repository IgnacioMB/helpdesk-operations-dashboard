"""Reproduces the evidence that resolution_timestamp is generated, not measured.

Usage:  python tools/demo_synthetic_tat.py
"""
import pathlib
import numpy as np
import pandas as pd

RAW = pathlib.Path(__file__).resolve().parent.parent / "Casestudy-Kiwi.com-BusinessAnalyst.xlsx"
raw = pd.read_excel(RAW, sheet_name="fact_ticket", dtype=object)
c = pd.to_datetime(raw["creation_timestamp_utc"])
r = pd.to_datetime(raw["resolution_timestamp_utc"])
tat = (r - c).dt.total_seconds() / 60

print("1. Raw timestamps - seconds AND microseconds are copied across:")
for i in [0, 1, 2, 3, 7]:
    print(f"   {c[i]:%Y-%m-%d %H:%M:%S.%f}  ->  {r[i]:%Y-%m-%d %H:%M:%S.%f}   {tat[i]:.0f} min")
same = ((c.dt.second == r.dt.second) & (c.dt.microsecond == r.dt.microsecond))
print(f"   identical in {same.sum():,} of {len(raw):,} rows ({100 * same.mean():.4f}%)")
print(f"   rows with a non-zero microsecond part: {(c.dt.microsecond != 0).sum():,} "
      f"(so the match is not vacuous)\n")

print(f"2. Gap is always whole minutes: {bool((tat % 1 == 0).all())}")
print(f"3. Hard walls: min {tat.min():.0f}, max {tat.max():.0f}; "
      f"{(tat < 15).sum()} under 15, {(tat > 45).sum()} over 45")
vc = tat.round().astype(int).value_counts()
print(f"4. Flat: each of the 31 values occurs {vc.min()}-{vc.max()} times (mean {vc.mean():.0f})\n")

print("5. Median does not rescue it - there is no tail to protect against:")
print(f"   mean {tat.mean():.2f}   median {tat.median():.2f}   skewness {tat.skew():.4f} "
      f"(real handling-time data is strongly right-skewed)")
print(f"   p99/median = {tat.quantile(.99) / tat.median():.2f}x\n")

print("6. Fresh random draws of the same size are indistinguishable:")
rng = np.random.default_rng(0)
for _ in range(5):
    s = rng.integers(15, 46, len(tat))
    print(f"   simulated  mean {s.mean():.2f}  median {np.median(s):.1f}")
print(f"   REAL DATA  mean {tat.mean():.2f}  median {tat.median():.1f}")
