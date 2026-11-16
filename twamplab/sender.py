"""TWAMP-Light session sender: sends test packets and collects replies."""
from __future__ import annotations

import argparse
import csv
import json
import logging
import select
import socket
import sys
import time

from .analysis import Sample, build_report
from .packets import ReflectorPacket, SenderPacket

log = logging.getLogger("twamplab.sender")


def run_session(host: str, port: int = 862, count: int = 100, interval: float = 0.1,
                padding: int = 27, timeout: float = 2.0, dscp: int = 0) -> tuple[int, list[Sample]]:
    """Send ``count`` packets ``interval`` seconds apart; return (sent, samples)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if dscp:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, dscp << 2)
    sock.setblocking(False)
    dest = (host, port)
    samples: dict[int, Sample] = {}
    next_send = time.time()
    sent = 0

    def drain(until: float) -> None:
        while True:
            wait = until - time.time()
            if wait <= 0:
                return
            ready, _, _ = select.select([sock], [], [], wait)
            if not ready:
                return
            data, _ = sock.recvfrom(65535)
            t4 = time.time()
            try:
                r = ReflectorPacket.unpack(data)
            except ValueError as exc:
                log.warning("bad reply: %s", exc)
                continue
            if r.sender_seq in samples:
                continue  # duplicate
            samples[r.sender_seq] = Sample(r.sender_seq, r.sender_timestamp,
                                           r.receive_timestamp, r.timestamp, t4)

    try:
        for seq in range(count):
            drain(next_send)
            pkt = SenderPacket(seq=seq, timestamp=time.time())
            sock.sendto(pkt.pack(padding), dest)
            sent += 1
            next_send += interval
        drain(time.time() + timeout)
    finally:
        sock.close()
    return sent, list(samples.values())


def write_csv(path: str, report) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seq", "t1", "t2", "t3", "t4", "rtt_ms", "raw_forward_ms",
                    "raw_reverse_ms", "forward_ms", "reverse_ms"])
        for s in report.samples:
            fwd, rev = report.corrected(s)
            w.writerow([s.seq, f"{s.t1:.9f}", f"{s.t2:.9f}", f"{s.t3:.9f}", f"{s.t4:.9f}",
                        f"{s.rtt*1000:.4f}", f"{s.raw_forward*1000:.4f}",
                        f"{s.raw_reverse*1000:.4f}", f"{fwd*1000:.4f}", f"{rev*1000:.4f}"])


def print_summary(summary: dict) -> None:
    print(f"\nPackets: {summary['sent']} sent, {summary['received']} received, "
          f"{summary['loss_pct']:.2f}% loss")
    if summary["received"] == 0:
        return
    print(f"{'':<10}{'min':>9}{'avg':>9}{'p50':>9}{'p95':>9}{'max':>9}  (ms)")
    for key, label in (("rtt_ms", "RTT"), ("forward_ms", "Forward"), ("reverse_ms", "Reverse")):
        s = summary[key]
        print(f"{label:<10}{s['min']:9.3f}{s['avg']:9.3f}{s['p50']:9.3f}{s['p95']:9.3f}{s['max']:9.3f}")
    j = summary["jitter_ms"]
    print(f"Jitter (RFC 3550): RTT {j['rtt']:.3f} ms, forward {j['forward']:.3f} ms, "
          f"reverse {j['reverse']:.3f} ms")
    if "clock" in summary:
        c = summary["clock"]
        print(f"Clock: reflector offset {c['offset_ms_at_start']:+.3f} ms at start, "
              f"drift {c['drift_ppm']:+.1f} ppm ({c['samples_used']} low-RTT samples)")
    print(f"One-way mode: {summary['one_way_mode']}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="TWAMP-Light sender")
    p.add_argument("host")
    p.add_argument("--port", type=int, default=862)
    p.add_argument("-c", "--count", type=int, default=100)
    p.add_argument("-i", "--interval", type=float, default=0.1, help="seconds between packets")
    p.add_argument("--padding", type=int, default=27)
    p.add_argument("--dscp", type=int, default=0)
    p.add_argument("--timeout", type=float, default=2.0)
    p.add_argument("--assume-synced", action="store_true",
                   help="clocks are synced externally (PTP/GPS): skip offset estimation")
    p.add_argument("--csv", help="write per-packet results to this CSV file")
    p.add_argument("--json", help="write the summary to this JSON file")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.WARNING)

    sent, samples = run_session(a.host, a.port, a.count, a.interval, a.padding, a.timeout, a.dscp)
    report = build_report(sent, samples, a.assume_synced)
    summary = report.summary()
    print_summary(summary)
    if a.csv:
        write_csv(a.csv, report)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(summary, f, indent=2)
    if summary["received"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
