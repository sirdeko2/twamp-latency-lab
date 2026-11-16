import threading
from twamplab import reflector, sender
from twamplab.analysis import build_report


def test_end_to_end_over_loopback():
    ready = threading.Event()
    t = threading.Thread(target=reflector.serve,
                         kwargs=dict(host="127.0.0.1", port=18620, clock_offset=0.5,
                                     max_packets=50, ready=ready), daemon=True)
    t.start()
    ready.wait(2)
    sent, samples = sender.run_session("127.0.0.1", 18620, count=50, interval=0.005, timeout=1)
    rep = build_report(sent, samples).summary()
    assert rep["received"] == 50 and rep["loss_pct"] == 0
    assert rep["rtt_ms"]["avg"] < 50
    assert abs(rep["clock"]["offset_ms_at_start"] - 500) < 5
