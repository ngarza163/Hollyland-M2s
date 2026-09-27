"""Print the receiver's status, firmware versions and serial numbers (read-only)."""
import time

import hid

from larkm2s import protocol as P
from larkm2s.device import find_control_path


def main():
    path = find_control_path()
    if path is None:
        print("No Lark M2S receiver found. Plug it in and try again.")
        return
    h = hid.device()
    h.open_path(path)

    def ask(cmd, device=P.RX):
        h.write(P.build_report(cmd, device=device))
        end = time.time() + 1.0
        while time.time() < end:
            data = h.read(P.REPORT_SIZE, 50)
            reply = P.parse_report(bytes(data)) if data else None
            if reply and reply.cmd == cmd:
                return reply
        return None

    reply = ask(P.HEARTBEAT)
    print("Status:", P.Status.from_payload(reply.payload) if reply else "no reply")
    for device, name in ((P.RX, "Receiver"), (P.TX1, "Mic 1"), (P.TX2, "Mic 2")):
        version = ask(P.GET_VERSION, device)
        serial = ask(P.GET_SERIAL, device)
        print(f"{name:9s} firmware {P.version_string(version.payload) if version else '?':12s}"
              f" serial {P.serial_string(serial.payload) if serial else '?'}")
    speaker = ask(P.GET_PHONE_SPEAKER)
    print("Phone Speaker:", ("on" if speaker.payload[0] == 0 else "off") if speaker else "?")
    h.close()


if __name__ == "__main__":
    main()
