import random
from twamplab.analysis import Sample, build_report, rfc3550_jitter


def synth(n=500, fwd=0.020, rev=0.005, offset=0.250, drift_ppm=50, noise=0.002, seed=1):
    """Simulate a path with known one-way delays and a wrong reflector clock."""
    rnd = random.Random(seed)
    out, start = [], 1_700_000_000.0
    for i in range(n):
        t1 = start + i * 0.05
        d1 = fwd + rnd.expovariate(1 / noise)
        d2 = rev + rnd.expovariate(1 / noise)
        clock = lambda t: t + offset + (t - start) * drift_ppm * 1e-6
        t2_real = t1 + d1
        t3_real = t2_real + 0.0001
        out.append(Sample(i, t1, clock(t2_real), clock(t3_real), t3_real + d2))
    return out


def test_rtt_is_independent_of_clock_offset():
    s = synth(offset=5.0)
    rep = build_report(len(s), s)
    assert 24 < rep.summary()["rtt_ms"]["min"] < 27


def test_offset_and_drift_are_recovered_for_symmetric_path():
    s = synth(fwd=0.010, rev=0.010, offset=0.250, drift_ppm=50)
    rep = build_report(len(s), s)
    c = rep.summary()["clock"]
    assert abs(c["offset_ms_at_start"] - 250) < 1.0
    assert abs(c["drift_ppm"] - 50) < 15


def test_asymmetry_is_absorbed_into_offset_as_documented():
    # 20 ms forward, 5 ms reverse: without external sync the estimator sees
    # (20 - 5) / 2 = 7.5 ms of the asymmetry as clock offset.
    s = synth(fwd=0.020, rev=0.005, offset=0.0, drift_ppm=0)
    c = build_report(len(s), s).summary()["clock"]
    assert abs(c["offset_ms_at_start"] - 7.5) < 1.5


def test_loss_is_counted():
    s = synth(n=100)
    rep = build_report(120, s)
    assert abs(rep.summary()["loss_pct"] - 16.667) < 0.01


def test_jitter_of_constant_delay_is_zero():
    assert rfc3550_jitter([0.01] * 50) == 0.0
