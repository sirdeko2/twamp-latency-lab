"""Simulate a TWAMP run over a path with known delays and a wrong reflector clock.

Useful for demos and for checking the estimator without real hardware.
"""
from __future__ import annotations

import argparse
import random

from .analysis import Sample, build_report
from .sender import print_summary, write_csv


def simulate(n=1200, interval=0.05, fwd_ms=12.0, rev_ms=12.0, queue_ms=3.0,
             offset_ms=250.0, drift_ppm=100.0, loss=0.01, seed=7) -> tuple[int, list[Sample]]:
    rnd = random.Random(seed)
    start = 1_700_000_000.0
    clock = lambda t: t + offset_ms / 1000 + (t - start) * drift_ppm * 1e-6
    samples = []
    for i in range(n):
        if rnd.random() < loss:
            continue
        t1 = start + i * interval
        t2 = t1 + (fwd_ms + rnd.expovariate(1 / queue_ms)) / 1000
        t3 = t2 + 0.0001
        t4 = t3 + (rev_ms + rnd.expovariate(1 / queue_ms)) / 1000
        samples.append(Sample(i, t1, clock(t2), clock(t3), t4))
    return n, samples


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Simulate a TWAMP run")
    p.add_argument("--forward-ms", type=float, default=12.0)
    p.add_argument("--reverse-ms", type=float, default=12.0)
    p.add_argument("--offset-ms", type=float, default=250.0)
    p.add_argument("--drift-ppm", type=float, default=100.0)
    p.add_argument("--csv", default="simulated.csv")
    a = p.parse_args(argv)
    sent, samples = simulate(fwd_ms=a.forward_ms, rev_ms=a.reverse_ms,
                             offset_ms=a.offset_ms, drift_ppm=a.drift_ppm)
    rep = build_report(sent, samples)
    print_summary(rep.summary())
    write_csv(a.csv, rep)
    print(f"wrote {a.csv}")


if __name__ == "__main__":
    main()
