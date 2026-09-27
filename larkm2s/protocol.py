"""Hollyland Lark M2S (internal product "6302") USB HID control protocol.

Frames travel in 64-byte HID reports with report ID 0x55 on the receiver's
vendor collection (usage page 0xFF90):

    host -> RX:  55 | AA DD cmd ctl lenHi lenLo payload... xor | zero padding
    RX -> host:  55 | BB DD cmd ctl lenHi lenLo payload...     | zero padding

`xor` is the XOR of every frame byte before it (header included). The
receiver (firmware V2.0.0.9) does not append one to its replies.
`ctl` is 0x40 | device for requests (0 = RX, 1 = TX1, 2 = TX2); replies set
bit 7 (0x80 | device).

Command numbers and payload layouts come from Hollyland's HollyAudio app
(V1 protocol, used for product 6302) and their LarkM2SUpgrade PC tool.
"""
from dataclasses import dataclass

REPORT_ID = 0x55
REPORT_SIZE = 64
HOST_HEADER = b"\xAA\xDD"
DEVICE_HEADER = b"\xBB\xDD"

RX, TX1, TX2 = 0, 1, 2

# Commands
GET_BATTERY = 0x02
GET_VERSION = 0x03
GET_VOLUME = 0x04
SET_VOLUME = 0x05
SET_NOISE_LEVEL = 0x06
GET_DEVICE_ID = 0x08
RESTART = 0x0C
HEARTBEAT = 0x10
GET_NOISE_LEVEL = 0x11
SET_PHONE_SPEAKER = 0x12
GET_PHONE_SPEAKER = 0x13
GET_SERIAL = 0x15
SET_VOICE_MODE = 0x18
TOGGLE_NOISE = 0x19
SET_VOLUME_LOCK = 0x34
GET_VOLUME_LOCK = 0x35
SET_SHUTDOWN_TIME = 0x36
SET_LIGHT = 0x39


def checksum(data: bytes) -> int:
    x = 0
    for b in data:
        x ^= b
    return x


def build_report(cmd: int, payload: bytes = b"", device: int = RX) -> bytes:
    """Return the 64-byte output report (report ID included) for a request."""
    if len(payload) > REPORT_SIZE - 8:
        raise ValueError("payload too long")
    frame = HOST_HEADER + bytes([cmd, 0x40 | (device & 0x0F), len(payload) >> 8, len(payload) & 0xFF]) + payload
    frame += bytes([checksum(frame)])
    return (bytes([REPORT_ID]) + frame).ljust(REPORT_SIZE, b"\0")


@dataclass
class Reply:
    cmd: int
    device: int
    payload: bytes


def parse_report(report: bytes):
    """Extract a reply frame from an input report, or return None."""
    start = report.find(DEVICE_HEADER)
    if start < 0 or len(report) < start + 6:
        return None
    cmd, ctl, hi, lo = report[start + 2:start + 6]
    length = (hi << 8) | lo
    end = start + 6 + length
    if end > len(report):
        return None
    return Reply(cmd, ctl & 0x0F, bytes(report[start + 6:end]))


@dataclass
class Status:
    """Decoded heartbeat (0x10) reply."""
    tx1_connected: bool
    tx2_connected: bool
    tx1_battery: int
    tx2_battery: int
    level: int              # raw 16-bit value the app calls "uv"
    noise: int = None       # 0 off, 1 weak, 2 strong
    volume: int = None      # 0-5 (shown as 1-6)
    volume_locked: bool = None
    stereo: bool = None
    never_shutdown: bool = None
    button1: int = None
    button2: int = None
    light_on: bool = None

    @classmethod
    def from_payload(cls, p: bytes):
        if len(p) < 6:
            return None
        s = cls(p[0] == 1, p[1] == 1, p[2], p[3], int.from_bytes(p[4:6], "big", signed=True))
        opt = lambda i: p[i] if len(p) > i else None
        s.noise = opt(6)
        s.volume = opt(7)
        s.volume_locked = None if opt(8) is None else p[8] == 1
        s.stereo = None if opt(9) is None else p[9] == 1
        s.never_shutdown = None if opt(10) is None else p[10] == 1
        s.button1 = opt(11)
        s.button2 = opt(12)
        s.light_on = None if opt(13) is None else p[13] == 0
        return s


def version_string(payload: bytes) -> str:
    return "V" + ".".join(str(b) for b in payload)


def serial_string(payload: bytes) -> str:
    return payload.decode("ascii", errors="replace").strip("\0 ")
