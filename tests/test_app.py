"""Offline UI-logic tests (no receiver needed). Run from the project folder:  python -m tests.test_app"""
import queue
import tkinter as tk
from unittest import mock

import app
from larkm2s import device, protocol as P

# Never run the USB worker here: commands queued by these tests must not reach a real receiver.
device.Receiver.start = lambda self: None
device.Receiver.stop = lambda self: None


def make_app():
    root = tk.Tk()
    root.withdraw()
    a = app.App(root)
    a.connected = True
    a.status = P.Status.from_payload(bytes([1, 0, 90, 0, 0, 0, 2, 4, 0, 0, 0]))
    return root, a


def queued(a):
    items = []
    try:
        while True:
            items.append(a.rx._outbox.get_nowait()[0])
    except queue.Empty:
        return items


def test_computer_speakers_cancel_sends_nothing():
    root, a = make_app()
    try:
        with mock.patch.object(app.messagebox, "askyesno", return_value=False) as ask:
            a._set_speaker(False)
        assert ask.called
        assert queued(a) == []
    finally:
        a._close()


def test_computer_speakers_confirm_sends_command():
    root, a = make_app()
    try:
        with mock.patch.object(app.messagebox, "askyesno", return_value=True):
            a._set_speaker(False)
        assert queued(a) == [P.SET_PHONE_SPEAKER]
    finally:
        a._close()


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("ok  ", name)
            except Exception as exc:
                failed += 1
                print("FAIL", name, "-", type(exc).__name__, exc)
    raise SystemExit(1 if failed else 0)
