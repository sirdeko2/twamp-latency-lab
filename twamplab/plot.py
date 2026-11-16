"""Plot a sender CSV: RTT, raw forward delay with the fitted clock offset, and corrected one-way delays."""
from __future__ import annotations

import argparse
import csv

from .analysis import Sample, build_report


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Plot TWAMP results")
    p.add_argument("csv")
    p.add_argument("-o", "--output", default="twamp_results.png")
    a = p.parse_args(argv)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = list(csv.DictReader(open(a.csv)))
    samples = [Sample(int(r["seq"]), float(r["t1"]), float(r["t2"]), float(r["t3"]), float(r["t4"]))
               for r in rows]
    rep = build_report(len(samples), samples)
    t0 = samples[0].t1
    t = [s.t1 - t0 for s in samples]
    fwd, rev = zip(*(rep.corrected(s) for s in samples))

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(t, [s.rtt * 1000 for s in samples], color="#1f3864", lw=0.8)
    axes[0].set_ylabel("RTT (ms)")
    axes[0].set_title("Round-trip time (no clock sync needed)")
    axes[1].plot(t, [s.raw_forward * 1000 for s in samples], color="#999999", lw=0.8,
                 label="raw forward = delay + clock offset")
    axes[1].plot(t, [rep.offset.at(s.t1) * 1000 for s in samples], color="#e67e22", lw=2,
                 label=f"fitted offset ({rep.offset.drift_ppm:+.0f} ppm drift)")
    axes[1].set_ylabel("ms")
    axes[1].set_title("Raw one-way delay is dominated by the clock error")
    axes[1].legend(loc="upper left", fontsize=8)
    axes[2].plot(t, [x * 1000 for x in fwd], color="#c0392b", lw=0.8, label="forward")
    axes[2].plot(t, [x * 1000 for x in rev], color="#2e86c1", lw=0.8, label="reverse")
    axes[2].set_ylabel("one-way delay (ms)")
    axes[2].set_xlabel("time (s)")
    axes[2].set_title("Corrected one-way delays")
    axes[2].legend(loc="upper right", fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(a.output, dpi=130)
    print(f"saved {a.output}")


if __name__ == "__main__":
    main()
