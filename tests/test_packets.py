import time
from twamplab.packets import (REFLECTOR_HEADER_LEN, SENDER_HEADER_LEN, ReflectorPacket,
                              SenderPacket, from_ntp, to_ntp)


def test_header_sizes_match_rfc5357():
    assert SENDER_HEADER_LEN == 14
    assert REFLECTOR_HEADER_LEN == 41


def test_ntp_roundtrip_is_sub_microsecond():
    now = time.time()
    assert abs(from_ntp(to_ntp(now)) - now) < 1e-6


def test_sender_roundtrip():
    p = SenderPacket(seq=42, timestamp=1_700_000_000.123456)
    data = p.pack(padding=27)
    assert len(data) == 14 + 27
    q = SenderPacket.unpack(data)
    assert q.seq == 42 and abs(q.timestamp - p.timestamp) < 1e-6


def test_reflector_roundtrip():
    r = ReflectorPacket(7, 1_700_000_001.5, 0x8001, 1_700_000_001.4, 42,
                        1_700_000_000.1, 0x8001, 64)
    q = ReflectorPacket.unpack(r.pack())
    assert (q.seq, q.sender_seq, q.sender_ttl) == (7, 42, 64)
    assert abs(q.receive_timestamp - r.receive_timestamp) < 1e-6
