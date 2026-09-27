"""Background USB HID link to the Lark M2S receiver.

A worker thread owns the HID handle: it (re)opens the receiver's control
collection, sends queued requests one at a time (waiting briefly for each
reply, like HollyAudio's command queue), polls the heartbeat every second and
posts events to `Receiver.events`:

    ("connected", None) | ("disconnected", None) | ("reply", protocol.Reply)
"""
import queue
import threading
import time

import hid

from . import protocol as P

VENDOR_ID = 0x3547
PRODUCT_IDS = (0x0405, 0x0406)       # 6302 mobile (USB-C) and camera receivers
CONTROL_USAGE_PAGE = 0xFF90
HEARTBEAT_INTERVAL = 1.0
REPLY_TIMEOUT = 0.3


def find_control_path():
    for pid in PRODUCT_IDS:
        for d in hid.enumerate(VENDOR_ID, pid):
            if d["usage_page"] == CONTROL_USAGE_PAGE:
                return d["path"]
    return None


class Receiver:
    def __init__(self):
        self.events = queue.Queue()
        self._outbox = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="lark-m2s-usb", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)

    def send(self, cmd, payload=b"", device=P.RX):
        self._outbox.put((cmd, P.build_report(cmd, payload, device)))

    def _run(self):
        while not self._stop.is_set():
            path = find_control_path()
            if path is None:
                self._stop.wait(1.0)
                continue
            h = hid.device()
            try:
                h.open_path(path)
            except OSError:
                self._stop.wait(1.0)
                continue
            self.events.put(("connected", None))
            try:
                self._serve(h)
            except (OSError, ValueError):
                pass  # unplugged or restarted
            finally:
                h.close()
            self._discard_outbox()
            self.events.put(("disconnected", None))
            self._stop.wait(0.5)

    def _serve(self, h):
        next_beat = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= next_beat:
                self._transact(h, P.HEARTBEAT, P.build_report(P.HEARTBEAT))
                next_beat = time.monotonic() + HEARTBEAT_INTERVAL
            try:
                cmd, report = self._outbox.get_nowait()
            except queue.Empty:
                self._read(h, 50)
                continue
            self._transact(h, cmd, report)

    def _transact(self, h, cmd, report):
        if h.write(report) < 0:
            raise OSError("write failed")
        deadline = time.monotonic() + REPLY_TIMEOUT
        while time.monotonic() < deadline:
            reply = self._read(h, 20)
            if reply is not None and reply.cmd == cmd:
                return

    def _read(self, h, timeout_ms):
        # timeout_ms must be > 0: hidapi's read(n, 0) blocks until a report arrives,
        # and the receiver only sends reports in reply to a request.
        data = h.read(P.REPORT_SIZE, timeout_ms)
        if not data:
            return None
        reply = P.parse_report(bytes(data))
        if reply is not None:
            self.events.put(("reply", reply))
        return reply

    def _discard_outbox(self):
        try:
            while True:
                self._outbox.get_nowait()
        except queue.Empty:
            pass
