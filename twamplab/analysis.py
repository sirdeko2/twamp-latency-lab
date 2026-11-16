"""Turn raw TWAMP timestamps into latency metrics.

Each reply gives four timestamps:
  T1  sender transmit      (sender clock)
  T2  reflector receive    (reflector clock)
  T3  reflector transmit   (reflector clock)
  T4  sender receive       (sender clock)

Round-trip time needs no clock sync:  RTT = (T4 - T1) - (T3 - T2)

One-way delays mix real delay with the clock difference between the hosts:
  raw_forward = T2 - T1 = d_fwd + offset
  raw_reverse = T4 - T3 = d_rev - offset

We estimate the offset the way NTP does (theta = ((T2-T1) + (T3-T4)) / 2),
but only from the lowest-RTT samples, where queueing noise is smallest, and we
fit a line through time so clock *drift* is removed as well as a fixed offset.

Honest limit: from round-trip data alone, path asymmetry and clock offset are
mathematically indistinguishable. Offset correction assumes the fastest
packets saw a symmetric path. If you need true absolute one-way delay, sync
both clocks externally (PTP or GPS) and pass ``assume_synced=True``.
One-way delay *variation* is accurate either way.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field


@dataclass
class Sample:
    seq: int
    t1: float
    t2: float
    t3: float
    t4: float

    @property
    def rtt(self) -> float:
        return (self.t4 - self.t1) - (self.t3 - self.t2)

    @property
    def raw_forward(self) -> float:
        return self.t2 - self.t1

    @property
    def raw_reverse(self) -> float:
        return self.t4 - self.t3

    @property
    def theta(self) -> float:
        return ((self.t2 - self.t1) + (self.t3 - self.t4)) / 2


@dataclass
class OffsetModel:
    """Clock offset of the reflector relative to the sender: offset(t) = a + b*(t - t0)."""
    a: float
    b: float
    t0: float
    samples_used: int

    def at(self, t: float) -> float:
        return self.a + self.b * (t - self.t0)

    @property
    def drift_ppm(self) -> float:
        return self.b * 1e6


def fit_offset(samples: list[Sample], best_fraction: float = 0.2) -> OffsetModel:
    """Fit offset(t) from the lowest-RTT samples (least queueing) by least squares."""
    if not samples:
        raise ValueError("no samples to fit")
    t0 = samples[0].t1
    # Keep the fastest packets in each slice of the run, so drift is sampled evenly over time.
    slices = max(1, min(10, len(samples) // 10))
    size = math.ceil(len(samples) / slices)
    chosen: list[Sample] = []
    for i in range(0, len(samples), size):
        chunk = sorted(samples[i:i + size], key=lambda s: s.rtt)
        chosen.extend(chunk[:max(1, int(len(chunk) * best_fraction))])
    xs = [s.t1 - t0 for s in chosen]
    ys = [s.theta for s in chosen]
    if len(chosen) < 2 or max(xs) - min(xs) < 1e-9:
        return OffsetModel(statistics.median(ys), 0.0, t0, len(chosen))
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    return OffsetModel(a, b, t0, len(chosen))


def rfc3550_jitter(delays: list[float]) -> float:
    """Interarrival jitter as defined in RFC 3550 (smoothed, gain 1/16)."""
    j = 0.0
    for prev, cur in zip(delays, delays[1:]):
        j += (abs(cur - prev) - j) / 16
    return j


def _pct(values: list[float], p: float) -> float:
    vs = sorted(values)
    k = (len(vs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return vs[lo] if lo == hi else vs[lo] + (vs[hi] - vs[lo]) * (k - lo)


def _stats_ms(values: list[float]) -> dict:
    ms = [v * 1000 for v in values]
    return {
        "min": min(ms), "avg": statistics.fmean(ms), "p50": _pct(ms, 0.5),
        "p95": _pct(ms, 0.95), "p99": _pct(ms, 0.99), "max": max(ms),
        "stdev": statistics.pstdev(ms),
    }


@dataclass
class Report:
    sent: int
    received: int
    samples: list[Sample] = field(repr=False)
    offset: OffsetModel | None
    assume_synced: bool

    @property
    def loss_pct(self) -> float:
        return 100.0 * (self.sent - self.received) / self.sent if self.sent else 0.0

    def corrected(self, s: Sample) -> tuple[float, float]:
        if self.assume_synced or self.offset is None:
            return s.raw_forward, s.raw_reverse
        off = self.offset.at(s.t1)
        return s.raw_forward - off, s.raw_reverse + off

    def summary(self) -> dict:
        if not self.samples:
            return {"sent": self.sent, "received": 0, "loss_pct": 100.0}
        fwd, rev = zip(*(self.corrected(s) for s in self.samples))
        rtts = [s.rtt for s in self.samples]
        out = {
            "sent": self.sent, "received": self.received,
            "loss_pct": round(self.loss_pct, 3),
            "rtt_ms": _stats_ms(rtts),
            "forward_ms": _stats_ms(list(fwd)),
            "reverse_ms": _stats_ms(list(rev)),
            "jitter_ms": {
                "rtt": rfc3550_jitter(rtts) * 1000,
                "forward": rfc3550_jitter(list(fwd)) * 1000,
                "reverse": rfc3550_jitter(list(rev)) * 1000,
            },
            "one_way_mode": "assumed synchronized clocks" if self.assume_synced
                            else "offset and drift estimated from lowest-RTT samples",
        }
        if self.offset and not self.assume_synced:
            out["clock"] = {
                "offset_ms_at_start": self.offset.a * 1000,
                "drift_ppm": self.offset.drift_ppm,
                "samples_used": self.offset.samples_used,
            }
        return out


def build_report(sent: int, samples: list[Sample], assume_synced: bool = False) -> Report:
    samples = sorted(samples, key=lambda s: s.seq)
    offset = None if (assume_synced or not samples) else fit_offset(samples)
    return Report(sent, len(samples), samples, offset, assume_synced)
