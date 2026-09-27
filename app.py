"""Lark M2S Control: a Windows desktop controller for the Hollyland Lark M2S."""
import ctypes
import os
import queue
import sys
import time
import tkinter as tk
import winreg
from tkinter import font as tkfont
from tkinter import messagebox

from larkm2s import protocol as P
from larkm2s.device import Receiver

APP_NAME = "Lark M2S Control"

DARK = dict(bg="#101317", card="#181c22", border="#252b33", text="#e9ecef", muted="#8f99a5",
            seg="#222830", seg_hover="#2b323c", accent="#ff7a1a", accent_text="#ffffff",
            track="#3a424c", knob="#ffffff", disabled="#4b525b", good="#3ecf8e", warn="#f5a524",
            bad="#f0524f")
LIGHT = dict(bg="#f2f3f5", card="#ffffff", border="#e2e5e9", text="#15181c", muted="#6a737d",
             seg="#eef0f3", seg_hover="#e3e6ea", accent="#f26b1d", accent_text="#ffffff",
             track="#c9ced4", knob="#ffffff", disabled="#c3c8ce", good="#1f9d63", warn="#c98a0b",
             bad="#d93b38")


def prefers_light_theme():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 1
    except OSError:
        return False


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


class Toggle(tk.Canvas):
    def __init__(self, master, app, command):
        self.app, self.command = app, command
        self.w, self.h = app.px(42), app.px(24)
        super().__init__(master, width=self.w, height=self.h, bg=app.t["card"],
                         highlightthickness=0, cursor="hand2")
        self.value, self.enabled = False, False
        self.bind("<Button-1>", lambda e: self.enabled and self.command(not self.value))
        self._draw()

    def set(self, value=None, enabled=None):
        if value is not None:
            self.value = bool(value)
        if enabled is not None:
            self.enabled = enabled
            self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def _draw(self):
        t, w, h = self.app.t, self.w, self.h
        fill = (t["accent"] if self.value else t["track"]) if self.enabled else t["disabled"]
        self.delete("all")
        self.create_oval(0, 0, h, h, fill=fill, outline=fill)
        self.create_oval(w - h, 0, w, h, fill=fill, outline=fill)
        self.create_rectangle(h / 2, 0, w - h / 2, h, fill=fill, outline=fill)
        pad = self.app.px(3)
        x = w - h + pad if self.value else pad
        self.create_oval(x, pad, x + h - 2 * pad, h - pad, fill=t["knob"], outline=t["knob"])


class Segmented(tk.Frame):
    def __init__(self, master, app, options, command):
        self.app, self.command = app, command
        super().__init__(master, bg=app.t["seg"])
        self.value, self.enabled, self.items = None, False, {}
        for i, (text, value) in enumerate(options):
            label = tk.Label(self, text=text, font=app.f_body, bg=app.t["seg"], fg=app.t["text"],
                             padx=app.px(10), pady=app.px(6))
            label.grid(row=0, column=i, sticky="nsew", padx=(app.px(3) if i == 0 else 1, app.px(3)),
                       pady=app.px(3))
            self.columnconfigure(i, weight=1, uniform="seg")
            label.bind("<Button-1>", lambda e, v=value: self._click(v))
            label.bind("<Enter>", lambda e, v=value: self._hover(v, True))
            label.bind("<Leave>", lambda e, v=value: self._hover(v, False))
            self.items[value] = label
        self._paint()

    def set(self, value=None, enabled=None):
        if value is not None:
            self.value = value
        if enabled is not None:
            self.enabled = enabled
        self._paint()

    def clear(self):
        self.value = None
        self._paint()

    def _click(self, value):
        if self.enabled and value != self.value:
            self.command(value)

    def _hover(self, value, inside):
        if self.enabled and value != self.value:
            self.items[value].configure(bg=self.app.t["seg_hover" if inside else "seg"])

    def _paint(self):
        t = self.app.t
        for value, label in self.items.items():
            selected = value == self.value
            if selected:
                bg = t["accent"] if self.enabled else t["disabled"]
                fg = t["accent_text"]
            else:
                bg, fg = t["seg"], t["text"] if self.enabled else t["muted"]
            label.configure(bg=bg, fg=fg, cursor="hand2" if self.enabled and not selected else "arrow")


class Battery(tk.Canvas):
    def __init__(self, master, app):
        self.app = app
        self.w, self.h = app.px(34), app.px(16)
        super().__init__(master, width=self.w, height=self.h, bg=app.t["card"], highlightthickness=0)
        self.set(None)

    def set(self, level):
        t, w, h, s = self.app.t, self.w, self.h, self.app.px(1)
        self.delete("all")
        body = w - 3 * s
        edge = t["muted"] if level is not None else t["disabled"]
        self.create_rectangle(s, s, body, h - s, outline=edge, width=s * 1.5)
        self.create_rectangle(body, h * 0.33, w - s, h * 0.67, fill=edge, outline=edge)
        if level is None:
            return
        color = t["good"] if level > 30 else t["warn"] if level > 15 else t["bad"]
        inner = 3 * s
        width = (body - s - 2 * inner) * max(0, min(level, 100)) / 100
        if width > 0:
            self.create_rectangle(s + inner, s + inner, s + inner + width, h - s - inner,
                                  fill=color, outline=color)


class App:
    HOLD = 1.8   # seconds a local change wins over the heartbeat while the RX applies it

    def __init__(self, root):
        self.root = root
        self.t = LIGHT if prefers_light_theme() else DARK
        self.scale = root.winfo_fpixels("1i") / 96
        family = "Segoe UI Variable Text" if "Segoe UI Variable Text" in tkfont.families() else "Segoe UI"
        self.f_title = tkfont.Font(family=family, size=17, weight="bold")
        self.f_head = tkfont.Font(family=family, size=11, weight="bold")
        self.f_body = tkfont.Font(family=family, size=10)
        self.f_small = tkfont.Font(family=family, size=9)

        self.connected = False
        self.status = None
        self.phone_speaker = None
        self.versions, self.serials = {}, {}
        self.holds = {}
        self._toast_after = None

        self._build()
        self._render()
        self.rx = Receiver()
        self.rx.start()
        root.after(40, self._pump)
        root.protocol("WM_DELETE_WINDOW", self._close)

    def px(self, v):
        return int(round(v * self.scale))

    # ---------- layout ----------
    def _build(self):
        t, root = self.t, self.root
        root.configure(bg=t["bg"])
        outer = tk.Frame(root, bg=t["bg"], padx=self.px(22), pady=self.px(18))
        outer.pack(fill="both", expand=True)

        head = tk.Frame(outer, bg=t["bg"])
        head.pack(fill="x")
        tk.Label(head, text="Lark M2S", font=self.f_title, bg=t["bg"], fg=t["text"]).pack(side="left")
        self.pill = tk.Label(head, font=self.f_small, padx=self.px(10), pady=self.px(3))
        self.pill.pack(side="left", padx=self.px(12), pady=(self.px(4), 0))
        self.restart_btn = tk.Label(head, text="Restart receiver", font=self.f_small, bg=t["bg"],
                                    fg=t["muted"], cursor="hand2")
        self.restart_btn.pack(side="right", pady=(self.px(6), 0))
        self.restart_btn.bind("<Button-1>", lambda e: self._restart())
        self.subtitle = tk.Label(outer, font=self.f_small, bg=t["bg"], fg=t["muted"], anchor="w")
        self.subtitle.pack(fill="x", pady=(self.px(2), self.px(14)))

        cols = tk.Frame(outer, bg=t["bg"])
        cols.pack(fill="both", expand=True)
        left = tk.Frame(cols, bg=t["bg"])
        right = tk.Frame(cols, bg=t["bg"])
        left.pack(side="left", fill="y", anchor="n")
        right.pack(side="left", fill="both", expand=True, padx=(self.px(14), 0))

        self.mics = [self._mic_card(left, i) for i in (1, 2)]

        card = self._card(left)
        self._row(card, "Auto power-off", "Turn mics off after 15 minutes without audio")
        self.shutdown = Segmented(card, self, [("15 min", False), ("Never", True)], self._set_shutdown)
        self.shutdown.pack(fill="x", pady=(self.px(10), 0))

        card = self._card(left)
        self.speaker_toggle = self._row(card, "Computer Speakers",
                                        "Keep sound on this PC's speakers while plugged in",
                                        lambda p: Toggle(p, self, self._set_speaker))
        self.light_frame = tk.Frame(card, bg=t["card"])
        self.light_frame.pack(fill="x", pady=(self.px(12), 0))
        self.light_toggle = self._row(self.light_frame, "Indicator light", None,
                                      lambda p: Toggle(p, self, self._set_light))
        self.light_note = self._last_subtitle

        card = self._card(right)
        self.noise_toggle = self._row(card, "Noise cancellation", "Reduce background noise",
                                      lambda p: Toggle(p, self, self._set_noise_on))
        self.noise_level = Segmented(card, self, [("Weak", 1), ("Strong", 2)], self._set_noise_level)
        self.noise_level.pack(fill="x", pady=(self.px(10), 0))

        card = self._card(right)
        self.lock_toggle = self._row(card, "Volume", "Receiver output level",
                                     lambda p: self._lock_control(p))
        self.volume = Segmented(card, self, [(str(i + 1), i) for i in range(6)], self._set_volume)
        self.volume.pack(fill="x", pady=(self.px(10), 0))

        card = self._card(right)
        self._row(card, "Channel mode", "Mono mixes both mics; Stereo puts each mic on its own side")
        self.mode = Segmented(card, self, [("Mono", False), ("Stereo", True)], self._set_stereo)
        self.mode.pack(fill="x", pady=(self.px(10), 0))

        self.hint = tk.Label(right, font=self.f_small, bg=t["bg"], fg=t["muted"], justify="left",
                             wraplength=self.px(320), anchor="w")
        self.hint.pack(fill="x")

        self.toast = tk.Label(outer, font=self.f_small, bg=t["bg"], fg=t["muted"], anchor="w")
        self.toast.pack(fill="x", pady=(self.px(8), 0))

    def _card(self, parent, pady=(0, 12)):
        frame = tk.Frame(parent, bg=self.t["card"], highlightbackground=self.t["border"],
                         highlightthickness=1, padx=self.px(16), pady=self.px(14))
        frame.pack(fill="x", pady=(self.px(pady[0]), self.px(pady[1])))
        return frame

    def _row(self, parent, title, subtitle, control_factory=None):
        row = tk.Frame(parent, bg=self.t["card"])
        row.pack(fill="x")
        text = tk.Frame(row, bg=self.t["card"])
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, font=self.f_head, bg=self.t["card"], fg=self.t["text"],
                 anchor="w").pack(fill="x")
        sub = tk.Label(text, text=subtitle or "", font=self.f_small, bg=self.t["card"],
                       fg=self.t["muted"], anchor="w", justify="left", wraplength=self.px(300))
        sub.pack(fill="x")
        self._last_subtitle = sub
        if control_factory is None:
            return None
        control = control_factory(row)
        control.pack(side="right", padx=(self.px(12), 0))
        return control

    def _lock_control(self, parent):
        box = tk.Frame(parent, bg=self.t["card"])
        tk.Label(box, text="Lock", font=self.f_small, bg=self.t["card"], fg=self.t["muted"]).pack(
            side="left", padx=(0, self.px(8)))
        toggle = Toggle(box, self, self._set_lock)
        toggle.pack(side="left")
        box.set = toggle.set
        return box

    def _mic_card(self, parent, number):
        card = self._card(parent)
        card.configure(width=self.px(240))
        top = tk.Frame(card, bg=self.t["card"])
        top.pack(fill="x")
        tk.Label(top, text=f"Mic {number}", font=self.f_head, bg=self.t["card"], fg=self.t["text"]).pack(side="left")
        battery_text = tk.Label(top, font=self.f_body, bg=self.t["card"], fg=self.t["text"])
        battery_text.pack(side="right")
        battery = Battery(top, self)
        battery.pack(side="right", padx=(0, self.px(6)))
        state = tk.Label(card, font=self.f_body, bg=self.t["card"], anchor="w")
        state.pack(fill="x", pady=(self.px(8), 0))
        detail = tk.Label(card, font=self.f_small, bg=self.t["card"], fg=self.t["muted"], anchor="w",
                          width=30)
        detail.pack(fill="x")
        return dict(battery=battery, battery_text=battery_text, state=state, detail=detail)

    # ---------- device events ----------
    def _pump(self):
        try:
            while True:
                kind, data = self.rx.events.get_nowait()
                if kind == "connected":
                    self._on_connected()
                elif kind == "disconnected":
                    self._on_disconnected()
                else:
                    self._on_reply(data)
        except queue.Empty:
            pass
        self.root.after(40, self._pump)

    def _on_connected(self):
        self.connected = True
        for dev in (P.RX, P.TX1, P.TX2):
            self.rx.send(P.GET_VERSION, device=dev)
        self.rx.send(P.GET_SERIAL)
        self.rx.send(P.GET_PHONE_SPEAKER)
        self._render()

    def _on_disconnected(self):
        self.connected, self.status, self.phone_speaker = False, None, None
        self.versions.clear()
        self.serials.clear()
        self.holds.clear()
        self._render()

    def _on_reply(self, r):
        if r.cmd == P.HEARTBEAT:
            old = self.status
            self.status = P.Status.from_payload(r.payload)
            if self.status and old:
                for dev, was, now in ((P.TX1, old.tx1_connected, self.status.tx1_connected),
                                      (P.TX2, old.tx2_connected, self.status.tx2_connected)):
                    if now and not was:
                        self.rx.send(P.GET_VERSION, device=dev)
        elif r.cmd == P.GET_VERSION and r.payload:
            self.versions[r.device] = P.version_string(r.payload)
        elif r.cmd == P.GET_SERIAL and r.payload:
            self.serials[r.device] = P.serial_string(r.payload)
        elif r.cmd == P.GET_PHONE_SPEAKER and r.payload:
            self.phone_speaker = r.payload[0] == 0
        elif r.cmd in (P.SET_VOLUME, P.SET_NOISE_LEVEL, P.TOGGLE_NOISE, P.SET_VOLUME_LOCK,
                       P.SET_VOICE_MODE, P.SET_SHUTDOWN_TIME, P.SET_LIGHT, P.SET_PHONE_SPEAKER):
            ok = P.set_succeeded(r)
            if not ok:
                self._show_toast("The receiver didn't accept that change", True)
                self.holds.clear()
            elif r.cmd == P.SET_PHONE_SPEAKER:
                self._show_toast("Saved. The receiver restarts in a few seconds to apply it.")
            else:
                self._show_toast("Saved")
            if r.cmd == P.SET_PHONE_SPEAKER:
                self.rx.send(P.GET_PHONE_SPEAKER)
        self._render()

    # ---------- state helpers ----------
    def _hold(self, key, value):
        self.holds[key] = (value, time.monotonic() + self.HOLD)

    def _get(self, key, device_value):
        held = self.holds.get(key)
        if held and time.monotonic() < held[1]:
            return held[0]
        self.holds.pop(key, None)
        return device_value

    def _mic_online(self):
        s = self.status
        return bool(s and (s.tx1_connected or s.tx2_connected))

    # ---------- actions ----------
    def _require_mic(self):
        if self._mic_online():
            return True
        self._show_toast("Turn on a mic first - this setting needs a connected mic", True)
        return False

    def _set_noise_on(self, on):
        if self._require_mic():
            self._hold("noise_on", on)
            self.rx.send(P.TOGGLE_NOISE, b"\x02")
            self._render()

    def _set_noise_level(self, level):
        if self._require_mic():
            self._hold("noise", level)
            self.rx.send(P.SET_NOISE_LEVEL, bytes([level]))
            self._render()

    def _set_volume(self, index):
        if self.status is None:
            return
        if self._get("volume_locked", self.status.volume_locked):
            self._show_toast("Volume is locked - unlock it first", True)
            return
        self._hold("volume", index)
        self.rx.send(P.SET_VOLUME, bytes([index]))
        self._render()

    def _set_lock(self, locked):
        self._hold("volume_locked", locked)
        self.rx.send(P.SET_VOLUME_LOCK, bytes([1 if locked else 0]))
        self._render()

    def _set_stereo(self, stereo):
        if self._require_mic():
            self._hold("stereo", stereo)
            self.rx.send(P.SET_VOICE_MODE, bytes([1 if stereo else 0]))
            self._render()

    def _set_shutdown(self, never):
        self._hold("never_shutdown", never)
        self.rx.send(P.SET_SHUTDOWN_TIME, bytes([1 if never else 0]))
        self._render()

    def _set_speaker(self, on):
        if not messagebox.askyesno(APP_NAME, "Changing this restarts the receiver.\n\nAudio from the "
                                             "mics will drop for a few seconds. Continue?",
                                   parent=self.root):
            return
        self._hold("speaker", on)
        self.rx.send(P.SET_PHONE_SPEAKER, bytes([0 if on else 1]))
        self._render()

    def _set_light(self, on):
        self._hold("light_on", on)
        self.rx.send(P.SET_LIGHT, bytes([0 if on else 1]))
        self._render()

    def _restart(self):
        if not self.connected:
            return
        if messagebox.askyesno(APP_NAME, "Restart the receiver?\n\nAudio from the mics will drop for a "
                                         "few seconds while it reboots.", parent=self.root):
            self.rx.send(P.RESTART)
            self._show_toast("Restarting receiver...")

    # ---------- rendering ----------
    def _render(self):
        t, s, live = self.t, self.status, self.connected and self.status is not None
        if self.connected:
            self.pill.configure(text="Connected", bg=t["good"], fg="#ffffff")
            parts = ["Receiver"]
            if P.RX in self.versions:
                parts.append(self.versions[P.RX])
            if P.RX in self.serials:
                parts.append(f"SN {self.serials[P.RX]}")
            self.subtitle.configure(text="  ·  ".join(parts))
        else:
            self.pill.configure(text="Not connected", bg=t["seg"], fg=t["muted"])
            self.subtitle.configure(text="Plug the Lark M2S USB-C receiver into this PC")
        self.restart_btn.configure(fg=t["muted"] if self.connected else t["disabled"],
                                   cursor="hand2" if self.connected else "arrow")

        for i, mic in enumerate(self.mics):
            on = bool(s and (s.tx1_connected if i == 0 else s.tx2_connected))
            level = (s.tx1_battery if i == 0 else s.tx2_battery) if on else None
            mic["battery"].set(level)
            mic["battery_text"].configure(text=f"{level}%" if level is not None else "")
            mic["state"].configure(text="Connected" if on else "Not connected",
                                   fg=t["good"] if on else t["muted"])
            ver = self.versions.get(P.TX1 if i == 0 else P.TX2)
            mic["detail"].configure(text=f"Firmware {ver}" if on and ver else " ")
        if live and not self._mic_online():
            self.hint.configure(text="Mics are off or out of range. Noise cancellation and channel "
                                     "mode need at least one connected mic.")
        else:
            self.hint.configure(text="")

        mic_ok = live and self._mic_online()
        noise = self._get("noise", s.noise if s else None)
        noise_on = self._get("noise_on", bool(noise) if noise is not None else None)
        self.noise_toggle.set(bool(noise_on), enabled=mic_ok and noise is not None)
        if noise_on:
            if noise in (1, 2):
                self.noise_level.set(noise, enabled=mic_ok)
            else:
                self.noise_level.clear()
                self.noise_level.set(enabled=mic_ok)
            self.noise_level.pack(fill="x", pady=(self.px(10), 0))
        else:
            self.noise_level.pack_forget()

        locked = self._get("volume_locked", s.volume_locked if s else None)
        self.lock_toggle.set(bool(locked), enabled=live and locked is not None)
        volume = self._get("volume", s.volume if s else None)
        if volume is None:
            self.volume.clear()
        self.volume.set(volume, enabled=live and volume is not None and not locked)

        stereo = self._get("stereo", s.stereo if s else None)
        if stereo is None:
            self.mode.clear()
        self.mode.set(stereo, enabled=mic_ok and stereo is not None)
        never = self._get("never_shutdown", s.never_shutdown if s else None)
        if never is None:
            self.shutdown.clear()
        self.shutdown.set(never, enabled=live and never is not None)

        speaker = self._get("speaker", self.phone_speaker)
        self.speaker_toggle.set(bool(speaker), enabled=live and speaker is not None)
        light = self._get("light_on", s.light_on if s else None)
        self.light_toggle.set(bool(light), enabled=live and light is not None)
        self.light_note.configure(
            text="Needs receiver firmware newer than V2.0.0.9" if live and light is None else "")

    def _show_toast(self, text, error=False):
        self.toast.configure(text=text, fg=self.t["bad"] if error else self.t["muted"])
        if self._toast_after:
            self.root.after_cancel(self._toast_after)
        self._toast_after = self.root.after(2600, lambda: self.toast.configure(text=""))

    def _close(self):
        self.rx.stop()
        self.root.destroy()


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Hollyland.LarkM2SControl")
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title(APP_NAME)
    icon = resource("assets/icon.png")
    if os.path.exists(icon):
        root.iconphoto(True, tk.PhotoImage(file=icon))
    App(root)
    root.update_idletasks()
    root.minsize(root.winfo_reqwidth(), root.winfo_reqheight())
    root.resizable(False, False)
    root.mainloop()


if __name__ == "__main__":
    main()
