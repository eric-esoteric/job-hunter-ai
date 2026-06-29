# jh_automation.py
"""
Browser-data capture engine for Job Hunter AI (standalone mode).

Hotkey detection strategy (per platform):

  Windows — Win32 RegisterHotKey API (ctypes, zero extra dependencies).
      Operates at OS kernel level using physical Virtual Key codes.
      Fully layout-independent: VK codes are hardware-position integers,
      unaffected by the active keyboard layout (Russian Cyrillic, Arabic,
      Hebrew, etc.).  The hotkey is registered in a dedicated daemon thread
      that runs a Win32 GetMessage loop.  Termination is clean and
      synchronous: stop() posts WM_QUIT via PostThreadMessageW using the
      Win32 TID (captured at run-time start) and then joins the thread.

  macOS / Linux — pynput keyboard.Listener with physical .vk inspection.
      Modifier state is tracked by Key enum membership (ctrl_l / ctrl_r /
      ctrl …), which pynput normalises cross-platform regardless of layout.
      The main key is matched by the .vk attribute (CoreGraphics hardware
      keycode on macOS; X11 evdev+8 hardware keycode on Linux) — bypassing
      the active keymap entirely, so hotkeys fire on any locale.
      Linux/Wayland: guarded by enforce_linux_subsystem_guard() which exits
      with a clear diagnostic if XDG_SESSION_TYPE == wayland (pynput's XTest
      injection and the hotkey Listener are both non-functional there).

Capture pipeline (daemon thread, fires on each hotkey press):
  A. Active-window security check: abort if foreground process is not a
     known browser (protects clipboard in password managers, IDEs, etc.).
  B. Back up current clipboard.
  C. Ctrl+L → Ctrl+C  →  read URL  →  Esc (return focus to page body).
  D. Ctrl+A → Ctrl+C  →  read full page DOM text.
  E. Verify clipboard content: not empty, not the URL, length > 200 chars.
  F. Restore original clipboard (unconditional finally block).
  G. Push vacancy payload into the shared queue.
     Every abort/failure path that runs AFTER notify_fn() has fired pushes
     a sentinel {"status": "failed", "error": "..."} so the queue consumer
     can always unblock and reset the UI loading state.

Configurable hotkey:
  Stored in config.json as {"mod1": "ctrl", "mod2": "shift", "key": "X"}.
  HotkeySpec.from_config() handles both the new dict format and the legacy
  pynput string "<ctrl>+<shift>+x" (automatic one-time migration).
  BrowserCaptureEngine.set_hotkey(spec) hot-swaps the registration at
  runtime without restarting the application.
"""

from __future__ import annotations

import os
import sys
import time
import hashlib
import threading
import platform
import subprocess
from dataclasses import dataclass

try:
    import pyperclip
    from pynput import keyboard as _pynput_keyboard
    from pynput.keyboard import KeyCode as _KeyCode
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False
    _pynput_keyboard = None
    _KeyCode = None

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# ── Physical VK / hardware-keycode tables for A–Z  (used by pynput fallback) ──
#
# These tables map UPPERCASE letter names to the platform-native integer that
# pynput exposes as KeyCode.vk when the corresponding physical key is pressed,
# regardless of the active keyboard layout.

# macOS: CoreGraphics / IOKit hardware keycodes (kVK_ANSI_*)
_DARWIN_KEY_VK: dict[str, int] = {
    "A": 0x00, "B": 0x0B, "C": 0x08, "D": 0x02, "E": 0x0E, "F": 0x03,
    "G": 0x05, "H": 0x04, "I": 0x22, "J": 0x26, "K": 0x28, "L": 0x25,
    "M": 0x2E, "N": 0x2D, "O": 0x1F, "P": 0x23, "Q": 0x0C, "R": 0x0F,
    "S": 0x01, "T": 0x11, "U": 0x20, "V": 0x09, "W": 0x0D, "X": 0x07,
    "Y": 0x10, "Z": 0x06,
}

# Linux/X11: evdev physical keycode + 8 offset (standard PC keyboard layout)
# These are keycodes for the physical key POSITION, not the printed symbol —
# invariant across all locale configurations.
_LINUX_KEY_VK: dict[str, int] = {
    "A": 38, "B": 56, "C": 54, "D": 40, "E": 26, "F": 41, "G": 42,
    "H": 43, "I": 31, "J": 44, "K": 45, "L": 46, "M": 58, "N": 57,
    "O": 32, "P": 33, "Q": 24, "R": 27, "S": 39, "T": 28, "U": 30,
    "V": 55, "W": 25, "X": 53, "Y": 29, "Z": 52,
}

# ── Platform-specific keys for the capture macro (Ctrl+L / Ctrl+A / Ctrl+C) ──
#
# These are KeyCode instances used by pynput.Controller for keyboard synthesis
# inside the browser (separate from the configurable detection hotkey).
# from_vk() targets the physical key position — layout-independent.

def _make_capture_key(darwin_vk: int, win32_vk: int, linux_vk: int) -> "_KeyCode | None":
    if not AUTOMATION_AVAILABLE:
        return None
    vk = darwin_vk if _OS == "Darwin" else (win32_vk if _OS == "Windows" else linux_vk)
    return _KeyCode.from_vk(vk)

_KEY_A = _make_capture_key(0x00, 65, 38)   # A: kVK_ANSI_A / VK_A / X11:38
_KEY_C = _make_capture_key(0x08, 67, 54)   # C: kVK_ANSI_C / VK_C / X11:54
_KEY_L = _make_capture_key(0x25, 76, 46)   # L: kVK_ANSI_L / VK_L / X11:46

# ── pynput modifier key frozensets  (used by _PynputHotkeyEngine) ──────────────

def _key_set(*attr_names: str) -> frozenset:
    """Build a frozenset of pynput Key enum members; skips attrs that don't exist."""
    if not AUTOMATION_AVAILABLE or _pynput_keyboard is None:
        return frozenset()
    result: set = set()
    for name in attr_names:
        try:
            result.add(getattr(_pynput_keyboard.Key, name))
        except AttributeError:
            pass
    return frozenset(result)

_CTRL_KEYS  = _key_set("ctrl", "ctrl_l", "ctrl_r")
_ALT_KEYS   = _key_set("alt",  "alt_l",  "alt_r",  "alt_gr")
_SHIFT_KEYS = _key_set("shift","shift_l","shift_r")
_WIN_KEYS   = _key_set("cmd",  "cmd_l",  "cmd_r")   # Win/Super/Cmd


def _mod_name_for_key(key: object) -> str | None:
    """Returns the normalised modifier name for a pynput Key enum, or None."""
    if key in _CTRL_KEYS:  return "ctrl"
    if key in _ALT_KEYS:   return "alt"
    if key in _SHIFT_KEYS: return "shift"
    if key in _WIN_KEYS:   return "win"
    return None


# ── HotkeySpec ────────────────────────────────────────────────────────────────

@dataclass
class HotkeySpec:
    """
    Structured, serialisable representation of a global hotkey combination.

    Stored in config.json as:
        {"mod1": "ctrl", "mod2": "shift", "key": "X"}

    mod1   Primary modifier:    "ctrl" | "alt" | "win"
    mod2   Secondary modifier:  "shift" | "none"
    key    Main key (A–Z):      uppercase single letter

    All methods that translate to platform APIs validate that the key is
    in A–Z; anything outside that range falls back to "X".
    """
    mod1: str = "ctrl"
    mod2: str = "shift"
    key:  str = "X"

    def __post_init__(self) -> None:
        """
        Normalise fields and enforce the no-bare-letter-hotkey invariant.

        Runs automatically after every __init__ call — from_dict(), from_config(),
        _from_legacy_string(), direct construction, and any future callers — so
        the invariant is guaranteed at the data-model level regardless of source.

        Safety rule: if both modifiers resolve to "none", RegisterHotKey would
        receive fsModifiers=0, globally hijacking the physical key across the
        entire OS (the key becomes untypeable anywhere until the process dies).
        When this is detected the spec is silently corrected to Ctrl+Alt so the
        app remains functional even when booted from a corrupted config.json.
        """
        self.mod1 = self.mod1.lower()
        self.mod2 = self.mod2.lower()
        k = self.key.upper()
        self.key = k[0] if k and k[0].isalpha() else "X"
        if self.mod1 == "none" and self.mod2 == "none":
            print(
                f"[HotkeySpec]: Unsafe config — both modifiers are 'none' for key "
                f"'{self.key}'. Registering a bare-letter hotkey would globally hijack "
                "that key system-wide. Auto-correcting to Ctrl+Alt."
            )
            self.mod1 = "ctrl"
            self.mod2 = "alt"

    # ── Construction ──────────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "HotkeySpec":
        return cls(mod1="ctrl", mod2="shift", key="X")

    @classmethod
    def from_dict(cls, d: dict) -> "HotkeySpec":
        key_raw = str(d.get("key", "X")).upper()
        return cls(
            mod1=str(d.get("mod1", "ctrl")).lower(),
            mod2=str(d.get("mod2", "shift")).lower(),
            key=key_raw[0] if key_raw and key_raw[0].isalpha() else "X",
        )

    @classmethod
    def from_config(cls, config: dict) -> "HotkeySpec":
        """
        Loads from app_config dict.  Handles both new dict format and the
        legacy pynput string "<ctrl>+<shift>+x" stored under "capture_hotkey".
        """
        raw = config.get("hotkey")
        if isinstance(raw, dict):
            return cls.from_dict(raw)
        legacy = config.get("capture_hotkey", "")
        if legacy and isinstance(legacy, str):
            return cls._from_legacy_string(legacy)
        return cls.default()

    @classmethod
    def _from_legacy_string(cls, s: str) -> "HotkeySpec":
        """Parse pynput-format string like '<ctrl>+<shift>+x'."""
        alias = {"control": "ctrl", "cmd": "win", "command": "win", "super": "win"}
        parts = [p.strip().strip("<>").lower() for p in s.split("+") if p.strip()]
        mods: list[str] = []
        key = ""
        for p in parts:
            p = alias.get(p, p)
            if p in ("ctrl", "alt", "shift", "win"):
                mods.append(p)
            elif len(p) == 1 and p.isalpha():
                key = p.upper()
        return cls(
            mod1=mods[0] if mods else "ctrl",
            mod2=mods[1] if len(mods) > 1 else "shift",
            key=key or "X",
        )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"mod1": self.mod1, "mod2": self.mod2, "key": self.key}

    # ── Display ───────────────────────────────────────────────────────────────

    def display(self) -> str:
        """Human-readable form: 'Ctrl + Shift + X'."""
        parts = [self.mod1.capitalize()]
        if self.mod2 != "none":
            parts.append(self.mod2.capitalize())
        parts.append(self.key.upper())
        return " + ".join(parts)

    # ── Platform translation ──────────────────────────────────────────────────

    def win32_vk(self) -> int:
        """Win32 Virtual Key code for the main key.  A–Z map to ASCII 65–90."""
        return ord(self.key.upper())  # VK_A = 65, VK_B = 66, … VK_Z = 90

    def win32_mod_flags(self) -> int:
        """Combination of Win32 MOD_* flags for mod1 + mod2."""
        _flag = {"ctrl": 0x0002, "alt": 0x0001, "shift": 0x0004, "win": 0x0008, "none": 0}
        return _flag.get(self.mod1, 0) | _flag.get(self.mod2, 0)

    def required_mods(self) -> frozenset:
        """Set of modifier name strings required for the pynput engine."""
        return frozenset(m for m in (self.mod1, self.mod2) if m != "none")

    def pynput_vk(self) -> int:
        """Platform-native hardware keycode for the main key (pynput fallback)."""
        letter = self.key.upper()
        if _OS == "Darwin":
            return _DARWIN_KEY_VK.get(letter, 0)
        if _OS == "Linux":
            return _LINUX_KEY_VK.get(letter, 0)
        return ord(letter)  # Windows fallback (Win32 engine used instead)


# ── Exception types ───────────────────────────────────────────────────────────

class PlatformSecurityException(RuntimeError):
    """Raised when the OS security subsystem prevents reliable automation."""


class ContentCaptureError(Exception):
    """
    Raised when the clipboard does not contain valid page text.

    Typical cause: the browser focus did not return to the page viewport
    after pressing Esc (address-bar → body transition failed), so Ctrl+A/C
    re-copied the URL rather than the full page DOM text.
    """


# ── Wayland guard ─────────────────────────────────────────────────────────────

def enforce_linux_subsystem_guard() -> None:
    """
    Aborts automation startup on native Wayland sessions.

    pynput relies on the X11 XTest extension for both key injection
    (Controller.press) and the Listener hook.  Native Wayland compositors
    do not expose XTest; injections are silently dropped and clipboard
    mutations never arrive, making the capture macro non-functional.

    Detection uses two independent env vars (neither is sufficient alone):
      XDG_SESSION_TYPE  — set to "wayland" by the display manager.
      WAYLAND_DISPLAY   — set to the compositor socket path.

    Raises PlatformSecurityException with actionable remediation text.
    Does nothing on non-Linux platforms.
    """
    if not sys.platform.startswith("linux"):
        return
    xdg  = os.environ.get("XDG_SESSION_TYPE", "").lower()
    wd   = os.environ.get("WAYLAND_DISPLAY",   "").lower()
    if xdg == "wayland" or "wayland" in wd:
        raise PlatformSecurityException(
            "CRITICAL: Job Hunter AI cannot run under a native Wayland session.\n"
            "Reason: Wayland's security model isolates global key injection and "
            "keystroke capture — the browser macro cannot function.\n"
            "Remediation: Select 'GNOME on Xorg' or any X11 session at the login "
            "screen and restart the application."
        )


# ── Win32 global hotkey engine ────────────────────────────────────────────────

class _Win32HotkeyThread(threading.Thread):
    """
    Registers a global hotkey via Win32 RegisterHotKey and runs a blocking
    GetMessage loop in this dedicated daemon thread.

    Why GetMessage instead of PeekMessage:
      GetMessage sleeps until a message arrives, consuming 0 CPU cycles.
      WM_HOTKEY is delivered to the thread whose message queue registered
      it — since we call RegisterHotKey inside run(), it arrives here.

    Termination flow:
      stop() retrieves the Win32 TID (set at the very start of run() via
      GetCurrentThreadId) and posts WM_QUIT with PostThreadMessageW, which
      causes GetMessage to return 0, exiting the loop cleanly. stop() then
      joins the thread (blocks up to 1 s) to guarantee UnregisterHotKey has
      executed before the caller registers a replacement combination.

    MOD_NOREPEAT (0x4000): prevents repeated WM_HOTKEY while the combo is
    held down — the capture pipeline should fire exactly once per press.
    """

    _WM_HOTKEY    = 0x0312
    _WM_QUIT      = 0x0012
    _MOD_NOREPEAT = 0x4000
    _HOTKEY_ID    = 0x3EA1   # Arbitrary int, unique within this process

    def __init__(self, spec: HotkeySpec, callback) -> None:
        super().__init__(daemon=True, name="Win32HotkeyThread")
        self._vk        = spec.win32_vk()
        self._mod_flags = spec.win32_mod_flags() | self._MOD_NOREPEAT
        self._callback  = callback
        self._win32_tid = 0         # Set inside run() before blocking on GetMessage
        self._ready     = threading.Event()  # Unblocks stop() after TID is captured

    def run(self) -> None:
        import ctypes
        import ctypes.wintypes

        self._win32_tid = ctypes.windll.kernel32.GetCurrentThreadId()
        # _ready is intentionally set AFTER RegisterHotKey: this guarantees
        # that any concurrent stop() calling _ready.wait() will only unblock
        # after the hotkey has been registered in this thread's message queue.
        # RegisterHotKey and UnregisterHotKey are both called from within this
        # dedicated thread, satisfying the Win32 thread-affinity requirement.
        registered = ctypes.windll.user32.RegisterHotKey(
            None, self._HOTKEY_ID, self._mod_flags, self._vk
        )
        self._ready.set()  # Unblock any concurrent stop() — registration attempt is done

        if not registered:
            err = ctypes.windll.kernel32.GetLastError()
            print(
                f"[Win32Hotkey]: RegisterHotKey failed (error {err}). "
                "The key combination may already be claimed by another application. "
                "Change the capture hotkey in Settings."
            )
            return

        print(
            f"[Win32Hotkey]: Registered — VK=0x{self._vk:02X}, "
            f"mods=0x{self._mod_flags & ~self._MOD_NOREPEAT:02X}"
        )

        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == self._WM_HOTKEY and msg.wParam == self._HOTKEY_ID:
                try:
                    self._callback()
                except Exception as exc:
                    print(f"[Win32Hotkey]: Callback raised: {exc}")

        ctypes.windll.user32.UnregisterHotKey(None, self._HOTKEY_ID)
        print("[Win32Hotkey]: Hotkey unregistered, message loop exited cleanly.")

    def stop(self) -> None:
        """Post WM_QUIT to the message loop thread and block until it exits."""
        self._ready.wait(timeout=1.0)
        if self._win32_tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(
                self._win32_tid, self._WM_QUIT, 0, 0
            )
        self.join(timeout=1.0)
        self._win32_tid = 0


# ── pynput hotkey engine (macOS / Linux) ──────────────────────────────────────

class _PynputHotkeyEngine:
    """
    Detects the configured hotkey on macOS and Linux using pynput's low-level
    Listener, which exposes raw hardware keycodes via KeyCode.vk.

    Modifier tracking uses Key enum membership rather than VK codes, because
    pynput normalises modifier Key objects consistently across platforms
    (Key.ctrl_l / Key.ctrl_r / Key.ctrl) regardless of keyboard layout.

    The main key is matched by comparing KeyCode.vk to the platform-native
    hardware keycode from HotkeySpec.pynput_vk(), which is layout-independent.

    Debounce: _main_fired is True while the key combination is held down,
    preventing repeated pipeline invocations from auto-repeat.
    """

    def __init__(self, spec: HotkeySpec, callback) -> None:
        self._target_vk    = spec.pynput_vk()
        self._required_mods = spec.required_mods()  # frozenset of str names
        self._callback     = callback
        self._mods_pressed: set[str] = set()
        self._main_fired   = False
        self._listener     = None

    def _on_press(self, key: object) -> None:
        mod = _mod_name_for_key(key)
        if mod is not None:
            self._mods_pressed.add(mod)
            return
        vk = getattr(key, "vk", None)
        if (vk == self._target_vk
                and self._required_mods.issubset(self._mods_pressed)
                and not self._main_fired):
            self._main_fired = True
            try:
                self._callback()
            except Exception as exc:
                print(f"[PynputHotkey]: Callback raised: {exc}")

    def _on_release(self, key: object) -> None:
        mod = _mod_name_for_key(key)
        if mod is not None:
            self._mods_pressed.discard(mod)
        if getattr(key, "vk", None) == self._target_vk:
            self._main_fired = False

    def start(self) -> None:
        self._listener = _pynput_keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            daemon=True,
        )
        self._listener.start()
        print(f"[PynputHotkey]: Listener started for VK=0x{self._target_vk:02X}")

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
                self._listener.join(timeout=0.5)
            except Exception as exc:
                print(f"[PynputHotkey]: Stop error: {exc}")
            self._listener = None
        self._mods_pressed.clear()
        self._main_fired = False


# ── Known browser process names (lowercase) ───────────────────────────────────

_BROWSER_PROCESS_NAMES = frozenset({
    # Windows executables
    "chrome.exe", "chromium.exe", "firefox.exe", "msedge.exe", "opera.exe",
    "brave.exe", "browser.exe", "vivaldi.exe", "waterfox.exe", "librewolf.exe",
    # macOS display names (from osascript)
    "google chrome", "chromium", "firefox", "safari", "microsoft edge", "opera",
    "brave browser", "yandex", "vivaldi", "waterfox", "librewolf",
    # Linux executable basenames
    "chrome", "chromium-browser", "firefox-esr", "opera", "brave",
    "brave-browser", "vivaldi", "epiphany", "midori", "waterfox", "librewolf",
})


# ── Active-window detection ───────────────────────────────────────────────────

def _get_active_process_name() -> str:
    """
    Returns the lowercase executable name of the process owning the focused
    window.  Returns "" on any failure — callers treat "" as unknown/allow.
    Never raises.

    Windows — QueryFullProcessImageNameW via ctypes (no extra deps).
    macOS   — AppleScript via osascript subprocess.
    Linux   — xdotool subprocess + /proc/<pid>/exe symlink.
    """
    try:
        if _OS == "Windows":
            import ctypes
            import ctypes.wintypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return ""
            pid = ctypes.wintypes.DWORD(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h_proc = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
            )
            if not h_proc:
                return ""
            try:
                buf  = ctypes.create_unicode_buffer(512)
                size = ctypes.wintypes.DWORD(512)
                ctypes.windll.kernel32.QueryFullProcessImageNameW(
                    h_proc, 0, buf, ctypes.byref(size)
                )
                return os.path.basename(buf.value).lower()
            finally:
                ctypes.windll.kernel32.CloseHandle(h_proc)

        elif _OS == "Darwin":
            result = subprocess.run(
                [
                    "osascript", "-e",
                    "tell application \"System Events\" "
                    "to get name of first process whose frontmost is true",
                ],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip().lower()

        else:  # Linux
            win_id_proc = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True, text=True, timeout=2,
            )
            if win_id_proc.returncode != 0:
                return ""
            pid_proc = subprocess.run(
                ["xdotool", "getwindowpid", win_id_proc.stdout.strip()],
                capture_output=True, text=True, timeout=2,
            )
            if pid_proc.returncode != 0:
                return ""
            exe = os.readlink(f"/proc/{pid_proc.stdout.strip()}/exe")
            return os.path.basename(exe).lower()

    except Exception:
        return ""


def _ctrl_key():
    """Returns the correct primary modifier for keyboard synthesis on this OS."""
    if not AUTOMATION_AVAILABLE:
        return None
    return _pynput_keyboard.Key.cmd if _OS == "Darwin" else _pynput_keyboard.Key.ctrl


def wait_for_clipboard_change(old_value: str, timeout: float = 2.0) -> str:
    """
    Polls pyperclip every 10 ms until the clipboard differs from old_value.
    Returns the new content, or old_value if the timeout elapses.
    Never raises — all pyperclip errors are silenced internally.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            current = pyperclip.paste()
        except Exception:
            time.sleep(0.01)
            continue
        if current != old_value:
            return current
        time.sleep(0.01)
    return old_value


def _clipboard_write(text: str, retries: int = 3) -> bool:
    """
    Write `text` to the clipboard with retry on transient lock errors.

    On Windows another process (e.g., a clipboard manager, antivirus, or a
    security tool) may hold the clipboard open for up to ~50 ms.  Three
    attempts with 50 ms spacing covers the vast majority of such collisions
    without adding any perceptible delay to the capture pipeline.

    Returns True if the write succeeded, False after all retries are exhausted.
    """
    for attempt in range(retries):
        try:
            pyperclip.copy(text)
            return True
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(0.05)
            else:
                print(
                    f"[Automation]: Clipboard write failed after {retries} attempts: {exc}"
                )
    return False


def _is_valid_page_content(text: str, url: str) -> bool:
    """
    Heuristic guard that rejects clipboard text which is clearly not a webpage.

    Catches the two most common race-condition artefacts:
      • User pressed a key between our Ctrl+C injection and our paste read,
        overwriting the clipboard with a single character or a short phrase.
      • The address bar was not dismissed, so we re-captured a URL or a short
        browser UI fragment.

    Deliberately conservative: a false-negative (rejecting real content) forces
    a retry from the verify loop; a false-positive (accepting noise) corrupts
    the vacancy record silently.  The 20-token floor is very easy for any
    real webpage to clear and very hard for accidental keystrokes to reach in
    the < 300 ms window of the verify loop.
    """
    if not text or len(text) < 200:
        return False
    if url and text.strip() == url.strip():
        return False
    if len(text.split()) < 20:
        return False
    return True


# ── BrowserCaptureEngine ──────────────────────────────────────────────────────

class BrowserCaptureEngine:
    """
    Registers a system-wide hotkey and, upon activation, runs a two-stage
    URL + page-text capture macro in a daemon thread.

    Security:      aborts immediately if the foreground window is not a known
                   browser — clipboard is never touched in other contexts.

    Layout safety: on Windows, RegisterHotKey uses VK codes (physical keys,
                   not characters).  On Linux/macOS, pynput Listener checks
                   .vk hardware codes.  Neither mechanism relies on .char or
                   string parsing.

    Queue contract: every code path that fires notify_fn() MUST push either
                   a success payload or a failure sentinel {"status": "failed"}
                   before returning, so the queue consumer can always unblock.

    Thread-safe:   all public methods are safe to call from any thread.
    """

    def __init__(
        self,
        vacancy_queue,
        app_ready_fn,
        hotkey_spec: HotkeySpec | None = None,
        notify_fn=None,
        warn_fn=None,
        capture_success_fn=None,
    ) -> None:
        self._queue               = vacancy_queue
        self._app_ready           = app_ready_fn
        self._notify              = notify_fn
        self._warn                = warn_fn
        self._capture_success_fn  = capture_success_fn
        self._hotkey_spec         = hotkey_spec or HotkeySpec.default()
        self._hotkey_engine       = None   # _Win32HotkeyThread | _PynputHotkeyEngine
        self._capture_in_progress = False
        self._lock                = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Register the global hotkey and begin listening."""
        if not AUTOMATION_AVAILABLE:
            print("[Automation]: pynput/pyperclip not installed — hotkey capture disabled.")
            return

        if _OS == "Windows":
            self._start_win32()
        else:
            self._start_pynput()

    def stop(self) -> None:
        """Unregister the hotkey and join the listener thread synchronously."""
        with self._lock:
            engine = self._hotkey_engine
            self._hotkey_engine = None
        if engine is not None:
            try:
                engine.stop()
            except Exception as exc:
                print(f"[Automation]: Error stopping hotkey engine: {exc}")

    def set_hotkey(self, spec: HotkeySpec) -> None:
        """
        Hot-swap the registered hotkey without restarting the application.
        stop() is synchronous, so the old OS hook is fully released before
        start() registers the new one — no hook collision possible.
        """
        with self._lock:
            self._hotkey_spec = spec
        self.stop()
        self.start()

    # ── Internal: engine startup ──────────────────────────────────────────────

    def _make_fire_fn(self):
        """Returns a thread-safe callback that spawns the capture pipeline."""
        def _on_hotkey():
            # Atomic check-and-set under _lock so two rapid hotkey presses
            # cannot both pass the False check and spawn concurrent pipelines.
            with self._lock:
                if self._capture_in_progress:
                    return
                self._capture_in_progress = True
            try:
                t = threading.Thread(target=self._capture_pipeline, daemon=True)
                t.name = "CaptureThread"
                t.start()
            except Exception as exc:
                print(f"[Automation]: Failed to start capture thread: {exc}")
                self._capture_in_progress = False  # pipeline never ran; reset
        return _on_hotkey

    def _start_win32(self) -> None:
        with self._lock:
            spec = self._hotkey_spec
        engine = _Win32HotkeyThread(spec, self._make_fire_fn())
        engine.start()
        with self._lock:
            self._hotkey_engine = engine
        print(f"[Automation]: Win32 hotkey engine started — {spec.display()}")

    def _start_pynput(self) -> None:
        try:
            enforce_linux_subsystem_guard()
        except PlatformSecurityException as exc:
            print(str(exc), file=sys.stderr)
            print(
                "[Automation]: Hotkey capture disabled. "
                "The app continues running without the browser macro feature.",
                file=sys.stderr,
            )
            return

        with self._lock:
            spec = self._hotkey_spec
        engine = _PynputHotkeyEngine(spec, self._make_fire_fn())
        engine.start()
        with self._lock:
            self._hotkey_engine = engine
        print(f"[Automation]: pynput hotkey engine started — {spec.display()}")

    # ── Internal: failure helper ──────────────────────────────────────────────

    def _push_failure(self, error: str) -> None:
        """
        Push a failure sentinel into the shared queue.

        Called on every abort/error path that occurs AFTER notify_fn() has
        fired so the queue consumer can unblock and reset the UI loading
        state.  Never raises — a failure inside _push_failure is logged
        and swallowed so it never masks the original error.
        """
        try:
            self._queue.put({
                "url": "", "text": "", "title": "",
                "status": "failed", "error": error,
            })
        except Exception as exc:
            print(f"[Automation]: _push_failure itself failed: {exc}")

    # ── Browser viewport refocus ──────────────────────────────────────────────

    def _refocus_browser_content(self, controller) -> None:
        """
        Shift keyboard focus to the browser's main page content area
        so that the subsequent Ctrl+A captures the full vacancy text rather
        than whatever sidebar widget or navigation element the user last
        clicked on.

        Windows: posts WM_LBUTTONDOWN/UP directly to the foreground window's
        client area without touching the system cursor — completely invisible
        to the user.  PostMessageW queues the click asynchronously; the 30 ms
        sleep gives Chrome's message pump one frame to process it.

        macOS / Linux: sends Escape to dismiss any focused widget and return
        keyboard focus to the document body.
        """
        if _OS == "Windows":
            try:
                import ctypes
                import ctypes.wintypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not hwnd:
                    return
                rect = ctypes.wintypes.RECT()
                ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect))
                # Target: horizontal centre, 35 % down from the top of the
                # client area — below address bar + bookmarks bar on every
                # browser, guaranteed to land in the main content viewport.
                cx = (rect.right - rect.left) // 2
                cy = max(120, int((rect.bottom - rect.top) * 0.35))
                # LPARAM for WM_LBUTTON*: low word = client-X, high word = client-Y
                lparam = (cy << 16) | (cx & 0xFFFF)
                # WM_LBUTTONDOWN = 0x0201, WM_LBUTTONUP = 0x0202, MK_LBUTTON = 0x0001
                ctypes.windll.user32.PostMessageW(hwnd, 0x0201, 0x0001, lparam)
                ctypes.windll.user32.PostMessageW(hwnd, 0x0202, 0x0000, lparam)
                time.sleep(0.03)
            except Exception as exc:
                print(f"[Automation]: Silent viewport refocus failed: {exc}")
        else:
            try:
                controller.press(_pynput_keyboard.Key.esc)
                controller.release(_pynput_keyboard.Key.esc)
                time.sleep(0.05)
            except Exception:
                pass

    # ── Capture pipeline ──────────────────────────────────────────────────────

    def _capture_pipeline(self) -> None:
        """
        Full capture sequence.  Runs in a dedicated daemon thread.

        Step ordering rationale:
          A. Active-window check — aborts before any clipboard or UI access so
             the user's clipboard is never disturbed in non-browser contexts.
          B. Clipboard backup — secured BEFORE notify_fn() fires.
          B2. Modifier release — the Win32 WM_HOTKEY arrives while Ctrl/Shift are
             still physically held.  Synthesising Ctrl+A while Shift is down sends
             Ctrl+Shift+A to Chrome, which opens the "Search Tabs" panel instead
             of selecting page content.  Releasing all modifiers here prevents
             that leakage on every subsequent keyboard synthesis step.
          C. notify_fn() — UI status update only; does not touch clipboard.
          D. URL capture (Ctrl+L → Ctrl+C → Esc)
          E. Page-text capture (Ctrl+A → Ctrl+C → Esc)
          F. Validation and queue push
          G. finally: restore original clipboard; send one final Esc; release latch.

        Queue contract: every path that calls notify_fn() MUST push either
        a success payload or _push_failure() before returning.

        _capture_in_progress is set True atomically in _make_fire_fn (under
        self._lock) before this method is called — do NOT set it again here.
        """
        # ── Step A: active-window security check ──────────────────────────────
        # An empty name means we couldn't detect the process (unsupported
        # platform config) — be permissive and allow the capture.
        active_proc = _get_active_process_name()
        if active_proc and active_proc not in _BROWSER_PROCESS_NAMES:
            print(
                f"[Automation]: Macro aborted — foreground process "
                f"'{active_proc}' is not a known browser."
            )
            if self._warn:
                try:
                    self._warn()
                except Exception:
                    pass
            else:
                try:
                    import jh_notifications
                    jh_notifications.send_notification(
                        "Job Hunter AI",
                        "Macro aborted: active window is not a browser.",
                    )
                except Exception:
                    pass
            self._capture_in_progress = False
            return

        # ── Clipboard section ─────────────────────────────────────────────────
        # From this point forward every exit path MUST push to the queue.
        original_clipboard = ""
        controller = None   # declared here so finally block can send cleanup Esc

        try:
            # Step B: back up clipboard BEFORE any automated action so that
            # notify_fn() timing cannot affect what we preserve.
            try:
                original_clipboard = pyperclip.paste()
            except Exception:
                original_clipboard = ""

            ctrl       = _ctrl_key()
            controller = _pynput_keyboard.Controller()

            # Step B2: Release any modifier keys that may still be physically
            # held from the detection hotkey (Ctrl, Shift, Alt, Win/Cmd).
            # Without this, synthesised Ctrl+A arrives at Chrome as Ctrl+Shift+A
            # (when Shift is still down), which opens Chrome's "Search Tabs"
            # panel instead of selecting page content.  The combined set of all
            # known modifier keys is _CTRL_KEYS | _SHIFT_KEYS | _ALT_KEYS | _WIN_KEYS.
            for _mod in (_CTRL_KEYS | _SHIFT_KEYS | _ALT_KEYS | _WIN_KEYS):
                try:
                    controller.release(_mod)
                except Exception:
                    pass
            time.sleep(0.05)  # one OS frame for the release events to propagate

            # Step C: immediate UI feedback
            if self._notify:
                try:
                    self._notify()
                except Exception:
                    pass

            # Step D: URL capture
            url = self._capture_url(ctrl, controller)

            # Step E: page text capture (may raise ContentCaptureError)
            raw_text = self._capture_page_text(ctrl, controller, url=url)

            # MD5 fallback if URL capture failed but text capture succeeded
            if not url and raw_text:
                digest = hashlib.md5(
                    raw_text.encode("utf-8", errors="replace")
                ).hexdigest()
                url = f"hash:{digest}"
                print(f"[Automation]: URL capture failed — using hash fallback: {url}")

            if not raw_text:
                print("[Automation]: Empty page text captured — aborting.")
                self._push_failure("empty_text")
                return

            if not self._app_ready():
                print("[Automation]: Assistant inactive — capture discarded.")
                self._push_failure("inactive")
                return

            payload = {"url": url, "text": raw_text, "title": "", "status": "success"}
            self._queue.put(payload)
            print(
                f"[Automation]: Queued — url={url[:80]!r}  text_len={len(raw_text)}"
            )
            if self._capture_success_fn:
                try:
                    self._capture_success_fn()
                except Exception as exc:
                    print(f"[Automation]: Capture success callback raised: {exc}")

        except ContentCaptureError as cce:
            print(f"[Automation]: Content capture failed — {cce}")
            self._push_failure("content_capture_error")

        except Exception as exc:
            print(f"[Automation]: Unhandled error in capture pipeline: {exc}")
            self._push_failure(str(exc))

        finally:
            # Each action is wrapped in its own try/except so that a failure
            # in clipboard restoration cannot skip the _capture_in_progress
            # reset and permanently block all future hotkey presses.
            try:
                _clipboard_write(original_clipboard)
            except Exception:
                pass

            try:
                if controller is not None:
                    controller.press(_pynput_keyboard.Key.esc)
                    controller.release(_pynput_keyboard.Key.esc)
            except Exception:
                pass

            self._capture_in_progress = False  # always reached

    def _capture_url(self, ctrl, controller) -> str:
        """
        Focus the address bar (Ctrl+L), copy the URL (Ctrl+C), then dismiss
        it (Esc).  _KEY_L and _KEY_C target physical key positions so the
        macro works on any keyboard layout.

        Uses _clipboard_write() for all pyperclip.copy() calls so transient
        clipboard-lock errors (another process briefly holding the clipboard)
        are retried rather than silently corrupting the capture.

        Returns the URL string, or "" on any failure.
        """
        try:
            _clipboard_write("")

            with controller.pressed(ctrl):
                controller.press(_KEY_L)
                controller.release(_KEY_L)
            time.sleep(0.05)   # address bar selected — imperceptible flash

            pre = pyperclip.paste()

            with controller.pressed(ctrl):
                controller.press(_KEY_C)
                controller.release(_KEY_C)

            candidate = wait_for_clipboard_change(pre, timeout=1.5)

            controller.press(_pynput_keyboard.Key.esc)
            controller.release(_pynput_keyboard.Key.esc)
            time.sleep(0.05)

            candidate = candidate.strip()
            return candidate if candidate.startswith(("http://", "https://")) else ""

        except Exception as exc:
            print(f"[Automation]: URL capture exception: {exc}")
            try:
                controller.press(_pynput_keyboard.Key.esc)
                controller.release(_pynput_keyboard.Key.esc)
            except Exception:
                pass
            return ""

    def _capture_page_text(self, ctrl, controller, url: str = "") -> str:
        """
        Select all page content (Ctrl+A) and copy it (Ctrl+C), then verify
        the clipboard contains real vacancy text using _is_valid_page_content().

        Focus strategy: _refocus_browser_content() is called first to move
        keyboard focus to the browser's main content area regardless of where
        the user's cursor or the previous keyboard focus was.  On Windows this
        is a save/click/restore mouse sequence (~35 ms, invisible); on other
        platforms it sends Escape to dismiss any focused sidebar widget.

        Verification loop (6 × 50 ms = 300 ms of additional slack):
          _is_valid_page_content() checks: length > 200, not equal to URL,
          word count ≥ 20.  The 20-token floor rejects accidental keystrokes
          (e.g., user typed during the capture window) without false-positives
          on real pages.

        Clipboard write via _clipboard_write() retries on transient lock errors
        so a momentary clipboard hold by antivirus / clipboard manager does not
        abort the capture with an opaque empty-text failure.

        Raises ContentCaptureError if all retries are exhausted.
        """
        try:
            # Ensure Ctrl+A targets the page body, not a focused sidebar element.
            self._refocus_browser_content(controller)

            if not _clipboard_write(""):
                raise ContentCaptureError("Clipboard locked — could not clear before Ctrl+A+C.")
            time.sleep(0.05)

            with controller.pressed(ctrl):
                controller.press(_KEY_A)
                controller.release(_KEY_A)
            time.sleep(0.10)

            with controller.pressed(ctrl):
                controller.press(_KEY_C)
                controller.release(_KEY_C)

            # Immediately deselect after copy so the blue page-wide highlight
            # disappears at once rather than lingering until the user moves focus.
            # This Esc is safe here: the content is already in the clipboard and
            # the verify loop below reads from the clipboard, not from the selection.
            try:
                controller.press(_pynput_keyboard.Key.esc)
                controller.release(_pynput_keyboard.Key.esc)
            except Exception:
                pass

            wait_for_clipboard_change("", timeout=5.0)

            for _ in range(6):
                try:
                    candidate = pyperclip.paste().strip()
                except Exception:
                    time.sleep(0.05)
                    continue
                if _is_valid_page_content(candidate, url):
                    return candidate
                time.sleep(0.05)

            try:
                final = pyperclip.paste().strip()
            except Exception:
                final = ""
            raise ContentCaptureError(
                f"Clipboard did not contain valid page content after 6 retries "
                f"(len={len(final)}, words={len(final.split())}, "
                f"matches_url={final == url}). "
                "The browser focus may not have returned to the page body after Esc."
            )

        except ContentCaptureError:
            raise
        except Exception as exc:
            print(f"[Automation]: Page-text capture exception: {exc}")
            return ""
        finally:
            # Guarantee the browser selection is visually cleared even when
            # ContentCaptureError propagates or an unexpected exception aborts
            # the verify loop before the inline Esc above had a chance to run.
            try:
                controller.press(_pynput_keyboard.Key.esc)
                controller.release(_pynput_keyboard.Key.esc)
            except Exception:
                pass
