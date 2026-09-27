"""Live checks for larkm2s.device.Receiver. Needs the receiver plugged in; sends read-only queries.

Run from the project folder:  python -m tests.live_check
"""
import queue
import sys
import time

from larkm2s import protocol as P
from larkm2s.device import Receiver


def collect(rx, seconds):
    replies = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            kind, data = rx.events.get(timeout=0.05)
        except queue.Empty:
            continue
        if kind == "reply":
            replies.append(data)
    return replies


def main():
    rx = Receiver()
    rx.start()
    failures = []
    try:
        beats = sum(r.cmd == P.HEARTBEAT for r in collect(rx, 4.5))
        print(f"heartbeat replies in 4.5 s: {beats}")
        if beats < 4:
            failures.append(f"heartbeat stopped polling ({beats} replies in 4.5 s, expected >= 4)")

        rx.send(P.GET_VERSION)          # queued while the worker is idle
        got = any(r.cmd == P.GET_VERSION for r in collect(rx, 1.0))
        print(f"request sent while idle got a reply: {got}")
        if not got:
            failures.append("request queued while idle was never sent")
    finally:
        rx.stop()
    for f in failures:
        print("FAIL:", f)
    print("PASS" if not failures else "FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
