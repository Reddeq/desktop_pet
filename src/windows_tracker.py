"""Read-only Win32 discovery. Hook callbacks only set a thread-safe dirty flag."""
import ctypes as C
from ctypes import wintypes as W
import os
import sys
import threading

from surfaces import Rect, Window


class WindowsTracker:
    def __init__(self):
        self.dirty = threading.Event()
        self.dirty.set()
        self.hooks = []
        self.supported = sys.platform == 'win32'
        self.error = None
        if not self.supported:
            return
        self.user = C.WinDLL('user32', use_last_error=True)
        self.dwm = C.WinDLL('dwmapi')
        self.enum_callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.event_callback = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND,
                                           W.LONG, W.LONG, W.DWORD, W.DWORD)
        prototypes = {
            'EnumWindows': ([self.enum_callback, W.LPARAM], W.BOOL),
            'IsWindowVisible': ([W.HWND], W.BOOL),
            'IsIconic': ([W.HWND], W.BOOL),
            'GetWindowRect': ([W.HWND, C.POINTER(W.RECT)], W.BOOL),
            'GetWindowThreadProcessId': ([W.HWND, C.POINTER(W.DWORD)], W.DWORD),
            'GetClassNameW': ([W.HWND, W.LPWSTR, C.c_int], C.c_int),
            'GetWindowTextLengthW': ([W.HWND], C.c_int),
            'GetWindowLongW': ([W.HWND, C.c_int], W.LONG),
            'GetWindow': ([W.HWND, W.UINT], W.HWND),
            'GetForegroundWindow': ([], W.HWND),
            'SetWinEventHook': ([W.DWORD, W.DWORD, W.HMODULE, self.event_callback,
                                 W.DWORD, W.DWORD, W.DWORD], W.HANDLE),
            'UnhookWinEvent': ([W.HANDLE], W.BOOL),
            'SetThreadDpiAwarenessContext': ([W.HANDLE], W.HANDLE),
        }
        for name, (arguments, result) in prototypes.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = arguments, result
        self.dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = C.c_long
        self._callback = self.event_callback(self._event)

    def _event(self, hook, event, hwnd, object_id, child, thread, time):
        if object_id == 0 and hwnd:
            self.dirty.set()

    def start(self):
        if not self.supported or self.hooks:
            return
        # Foreground, minimize/restore; object create/destroy/show/hide/reorder/
        # location changes. OUTOFCONTEXT + SKIPOWNPROCESS; no injected DLL.
        for low, high in ((3, 3), (0x16, 0x17), (0x8000, 0x8004), (0x800B, 0x800B)):
            hook = self.user.SetWinEventHook(low, high, None, self._callback, 0, 0, 2)
            if hook:
                self.hooks.append(hook)
            else:
                self.error = 'Windows event hook unavailable; periodic discovery remains active'

    def close(self):
        for hook in self.hooks:
            self.user.UnhookWinEvent(hook)
        self.hooks.clear()

    def window(self, hwnd):
        if not self.supported or not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):
            return None
        cloaked = W.DWORD()
        self.dwm.DwmGetWindowAttribute(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked))
        if cloaked.value:
            return None
        pid = W.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value == os.getpid():
            return None
        rect = W.RECT()
        # DWM visible frame bounds exclude the invisible resize border.
        result = self.dwm.DwmGetWindowAttribute(hwnd, 9, C.byref(rect), C.sizeof(rect))
        if result != 0 and not self.user.GetWindowRect(hwnd, C.byref(rect)):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        name = C.create_unicode_buffer(256)
        self.user.GetClassNameW(hwnd, name, len(name))
        desktop = name.value in {'Progman', 'WorkerW', 'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}
        style = self.user.GetWindowLongW(hwnd, -16)
        exstyle = self.user.GetWindowLongW(hwnd, -20)
        utility = (bool(exstyle & (0x80 | 0x08000000 | 0x20))
                   or bool(self.user.GetWindow(hwnd, 4))  # owned popup
                   or not self.user.GetWindowTextLengthW(hwnd)
                   or name.value in {'#32768', 'tooltips_class32'}
                   or bool(style & 0x40000000))
        return Window(int(hwnd), Rect(rect.left, rect.top, rect.right, rect.bottom),
                      utility=utility, desktop=desktop)

    def scan(self):
        if not self.supported:
            return (), None
        windows = []
        # Force physical coordinates for Win32 reads; restore the Qt thread's
        # DPI context immediately, including on failure.
        previous = self.user.SetThreadDpiAwarenessContext(W.HANDLE(-4))
        try:
            @self.enum_callback
            def collect(hwnd, parameter):
                window = self.window(hwnd)
                if window is not None:
                    windows.append(window)
                return True
            if not self.user.EnumWindows(collect, 0):
                raise OSError(C.get_last_error(), 'EnumWindows failed')
            return tuple(windows), self.user.GetForegroundWindow()
        finally:
            if previous:
                self.user.SetThreadDpiAwarenessContext(previous)

    def monitor_rects(self):
        if not self.supported:
            return {}
        class MonitorInfo(C.Structure):
            _fields_ = [('size', W.DWORD), ('monitor', W.RECT), ('work', W.RECT),
                        ('flags', W.DWORD), ('device', W.WCHAR * 32)]
        callback_type = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
        self.user.EnumDisplayMonitors.argtypes = [W.HDC, C.POINTER(W.RECT), callback_type, W.LPARAM]
        self.user.EnumDisplayMonitors.restype = W.BOOL
        self.user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
        self.user.GetMonitorInfoW.restype = W.BOOL
        result = {}
        @callback_type
        def collect(handle, dc, rect, parameter):
            info = MonitorInfo()
            info.size = C.sizeof(info)
            if self.user.GetMonitorInfoW(handle, C.byref(info)):
                r = info.monitor
                result[info.device] = Rect(r.left, r.top, r.right, r.bottom)
            return True
        self.user.EnumDisplayMonitors(None, None, collect, 0)
        return result
