"""Offline protocol tests. Run from the project folder:  python -m tests.test_protocol"""
from larkm2s import protocol as P


def test_toggle_noise_ack_counts_as_success():
    # The receiver acks 0x19 with 0x87 (now on) or 0x07 (now off), not 0x01.
    assert P.set_succeeded(P.Reply(P.TOGGLE_NOISE, P.RX, b"\x87"))
    assert P.set_succeeded(P.Reply(P.TOGGLE_NOISE, P.RX, b"\x07"))


def test_regular_set_acks():
    assert P.set_succeeded(P.Reply(P.SET_VOLUME, P.RX, b"\x01"))
    assert P.set_succeeded(P.Reply(P.SET_NOISE_LEVEL, P.RX, b"\x01\x02"))
    assert not P.set_succeeded(P.Reply(P.SET_VOLUME, P.RX, b"\x00"))
    assert not P.set_succeeded(P.Reply(P.SET_VOICE_MODE, P.RX, b""))


def test_build_report_frame():
    report = P.build_report(P.SET_VOLUME, b"\x04")
    assert len(report) == 64
    assert report[:9] == bytes([0x55, 0xAA, 0xDD, 0x05, 0x40, 0x00, 0x01, 0x04, 0xAA ^ 0xDD ^ 0x05 ^ 0x40 ^ 0x01 ^ 0x04])


def test_parse_heartbeat_reply():
    raw = bytes([0x55, 0xBB, 0xDD, 0x10, 0x80, 0x00, 0x0B, 1, 1, 98, 99, 0, 0, 0, 4, 0, 1, 0]).ljust(64, b"\0")
    reply = P.parse_report(raw)
    status = P.Status.from_payload(reply.payload)
    assert (reply.cmd, reply.device) == (P.HEARTBEAT, P.RX)
    assert status.tx1_connected and status.tx2_connected
    assert (status.tx1_battery, status.tx2_battery) == (98, 99)
    assert status.noise == 0 and status.volume == 4 and status.stereo
    assert status.light_on is None      # firmware V2.0.0.9 sends 11 bytes


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as exc:  # report every failing test, not just the first
                failed += 1
                print("FAIL", name, "-", type(exc).__name__, exc)
    raise SystemExit(1 if failed else 0)
