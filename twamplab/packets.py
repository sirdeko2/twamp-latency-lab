"""TWAMP-Test packet formats (RFC 5357, unauthenticated mode).

Timestamps use the NTP 64-bit format: 32-bit seconds since 1900-01-01 and a
32-bit binary fraction of a second.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01
DEFAULT_ERROR_ESTIMATE = 0x8001  # S=1 (synchronized), scale 0, multiplier 1

# Sender: seq(4) timestamp(8) error(2)
_SENDER = struct.Struct("!IQH")
# Reflector: seq(4) ts(8) err(2) mbz(2) rx_ts(8) sender_seq(4) sender_ts(8) sender_err(2) mbz(2) sender_ttl(1)
_REFLECTOR = struct.Struct("!IQHHQIQHHB")

SENDER_HEADER_LEN = _SENDER.size        # 14
REFLECTOR_HEADER_LEN = _REFLECTOR.size  # 41


def to_ntp(unix_seconds: float) -> int:
    """Convert a Unix time in seconds to a 64-bit NTP timestamp."""
    seconds = int(unix_seconds) + NTP_EPOCH_OFFSET
    fraction = int((unix_seconds - int(unix_seconds)) * (1 << 32)) & 0xFFFFFFFF
    return (seconds << 32) | fraction


def from_ntp(ntp: int) -> float:
    """Convert a 64-bit NTP timestamp to Unix time in seconds."""
    seconds = (ntp >> 32) - NTP_EPOCH_OFFSET
    fraction = (ntp & 0xFFFFFFFF) / (1 << 32)
    return seconds + fraction


@dataclass
class SenderPacket:
    seq: int
    timestamp: float  # Unix seconds (T1)
    error_estimate: int = DEFAULT_ERROR_ESTIMATE

    def pack(self, padding: int = 27) -> bytes:
        head = _SENDER.pack(self.seq, to_ntp(self.timestamp), self.error_estimate)
        return head + bytes(max(padding, 0))

    @classmethod
    def unpack(cls, data: bytes) -> "SenderPacket":
        if len(data) < SENDER_HEADER_LEN:
            raise ValueError(f"sender packet too short: {len(data)} bytes")
        seq, ts, err = _SENDER.unpack_from(data)
        return cls(seq, from_ntp(ts), err)


@dataclass
class ReflectorPacket:
    seq: int
    timestamp: float          # T3: reflector transmit time
    error_estimate: int
    receive_timestamp: float  # T2: reflector receive time
    sender_seq: int
    sender_timestamp: float   # T1: copied from the sender packet
    sender_error_estimate: int
    sender_ttl: int = 255

    def pack(self, padding: int = 0) -> bytes:
        head = _REFLECTOR.pack(
            self.seq, to_ntp(self.timestamp), self.error_estimate, 0,
            to_ntp(self.receive_timestamp), self.sender_seq,
            to_ntp(self.sender_timestamp), self.sender_error_estimate, 0,
            self.sender_ttl,
        )
        return head + bytes(max(padding, 0))

    @classmethod
    def unpack(cls, data: bytes) -> "ReflectorPacket":
        if len(data) < REFLECTOR_HEADER_LEN:
            raise ValueError(f"reflector packet too short: {len(data)} bytes")
        (seq, ts, err, _mbz1, rx_ts, s_seq, s_ts, s_err, _mbz2, ttl) = _REFLECTOR.unpack_from(data)
        return cls(seq, from_ntp(ts), err, from_ntp(rx_ts), s_seq, from_ntp(s_ts), s_err, ttl)
