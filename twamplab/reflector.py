"""TWAMP-Light session reflector.

Answers every TWAMP-Test packet it receives with a reflector packet carrying
its own receive (T2) and transmit (T3) timestamps.

For demos, ``clock_offset`` and ``clock_drift_ppm`` make the reflector's clock
deliberately wrong, so you can watch the sender estimate and remove the error.
"""
from __future__ import annotations

import argparse
import logging
import socket
import time

from .packets import ReflectorPacket, SenderPacket, error_estimate

log = logging.getLogger("twamplab.reflector")


class SkewedClock:
    """A clock that is ``offset`` seconds off and drifts by ``drift_ppm``."""

    def __init__(self, offset: float = 0.0, drift_ppm: float = 0.0):
        self.offset = offset
        self.drift = drift_ppm * 1e-6
        self.start = time.time()

    def now(self) -> float:
        real = time.time()
        return real + self.offset + (real - self.start) * self.drift


def serve(host: str = "0.0.0.0", port: int = 862, clock_offset: float = 0.0,
          clock_drift_ppm: float = 0.0, max_packets: int | None = None,
          ready=None, synced: bool = False) -> None:
    clock = SkewedClock(clock_offset, clock_drift_ppm)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    log.info("reflector listening on %s:%d (offset=%.3fs, drift=%.1fppm)",
             host, port, clock_offset, clock_drift_ppm)
    if ready is not None:
        ready.set()
    seq = 0
    handled = 0
    try:
        while max_packets is None or handled < max_packets:
            data, addr = sock.recvfrom(65535)
            t2 = clock.now()
            try:
                incoming = SenderPacket.unpack(data)
            except ValueError as exc:
                log.warning("dropping malformed packet from %s: %s", addr, exc)
                continue
            # Mirror the sender's size so the test stays symmetric (RFC 5357 sec 4.2.1)
            pad = max(len(data) - 41, 0)
            reply = ReflectorPacket(
                seq=seq, timestamp=clock.now(), error_estimate=error_estimate(synced),
                receive_timestamp=t2, sender_seq=incoming.seq,
                sender_timestamp=incoming.timestamp,
                sender_error_estimate=incoming.error_estimate,
            )
            sock.sendto(reply.pack(pad), addr)
            seq += 1
            handled += 1
    finally:
        sock.close()


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="TWAMP-Light reflector")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=862)
    p.add_argument("--clock-offset", type=float, default=0.0,
                   help="demo only: make this clock wrong by N seconds")
    p.add_argument("--clock-drift-ppm", type=float, default=0.0,
                   help="demo only: make this clock drift by N parts per million")
    p.add_argument("--synced", action="store_true",
                   help="this clock is externally synchronized (PTP/GPS): set the S flag")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    serve(a.host, a.port, a.clock_offset, a.clock_drift_ppm, synced=a.synced)


if __name__ == "__main__":
    main()
