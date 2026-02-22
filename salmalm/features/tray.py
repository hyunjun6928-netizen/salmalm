"""Windows System Tray for SalmAlm — pure ctypes implementation.

Provides a system tray icon with right-click menu on Windows.
On other platforms, falls back to normal server execution.
"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser

logger = logging.getLogger(__name__)


def is_windows() -> bool:
    return sys.platform == "win32"


def run_tray(port: int = 18800):
    """Run SalmAlm with system tray icon (Windows only).

    On non-Windows platforms, starts the server normally.
    """
    if not is_windows():
        logger.info("System tray is Windows-only. Starting normal server...")
        from .__main__ import main

        main()
        return

    _run_windows_tray(port)


def _run_windows_tray(port: int = 18800):
    """Windows system tray implementation using ctypes."""
    import ctypes
    import ctypes.wintypes as wt

    # ── Windows API constants ──
    WM_USER = 0x0400
    WM_TRAYICON = WM_USER + 1
    WM_COMMAND = 0x0111
    WM_DESTROY = 0x0002
    WM_RBUTTONUP = 0x0205
    WM_LBUTTONDBLCLK = 0x0203

    NIM_ADD = 0x00000000
    _NIM_MODIFY = 0x00000001  # noqa: F841
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004

    IDI_APPLICATION = 32512
    IMAGE_ICON = 1
    LR_SHARED = 0x8000

    WS_OVERLAPPED = 0x00000000
    _CW_USEDEFAULT = -2147483648  # 0x80000000 as signed  # noqa: F841

    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    TPM_LEFTALIGN = 0x0000
    TPM_RETURNCMD = 0x0100
    TPM_NONOTIFY = 0x0080

    # Menu IDs
    ID_OPEN_UI = 1001
    ID_NEW_CHAT = 1002
    ID_SETTINGS = 1003
    ID_QUIT = 1004

    # ── DLLs ──
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # ── NOTIFYICONDATAW structure ──
    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("hWnd", wt.HWND),
            ("uID", wt.UINT),
            ("uFlags", wt.UINT),
            ("uCallbackMessage", wt.UINT),
            ("hIcon", wt.HICON),
            ("szTip", wt.WCHAR * 128),
        ]

    # ── WNDCLASSW ──
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wt.UINT),
            ("lpfnWndProc", WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wt.HINSTANCE),
            ("hIcon", wt.HICON),
            ("hCursor", wt.HANDLE),
            ("hbrBackground", wt.HANDLE),
            ("lpszMenuName", wt.LPCWSTR),
            ("lpszClassName", wt.LPCWSTR),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", wt.LONG), ("y", wt.LONG)]

    class MSG(ctypes.Structure):
        _fields_ = [
            ("hWnd", wt.HWND),
            ("message", wt.UINT),
            ("wParam", wt.WPARAM),
            ("lParam", wt.LPARAM),
            ("time", wt.DWORD),
            ("pt", POINT),
        ]

    # ── Server thread ──
    _server_ref = [None]  # noqa: F841
    base_url = f"http://127.0.0.1:{port}"

    def start_server():
        """Start SalmAlm server in background thread."""
        from .__main__ import main

        main()

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Give server time to start
    import time

    time.sleep(2)

    # ── Window procedure ──
    hwnd_ref = [None]
    nid_ref = [None]

    def show_menu(hwnd):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, ID_OPEN_UI, "🌐 Open Web UI")
        user32.AppendMenuW(menu, MF_STRING, ID_NEW_CHAT, "💬 New Chat")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_SETTINGS, "⚙️ Settings")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "❌ Quit")

        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(menu, TPM_LEFTALIGN | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, hwnd, None)
        user32.DestroyMenu(menu)

        if cmd == ID_OPEN_UI:
            webbrowser.open(base_url)
        elif cmd == ID_NEW_CHAT:
            webbrowser.open(f"{base_url}/#new")
        elif cmd == ID_SETTINGS:
            webbrowser.open(f"{base_url}/#settings")
        elif cmd == ID_QUIT:
            _cleanup_and_quit(hwnd)

    def _cleanup_and_quit(hwnd):
        if nid_ref[0]:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid_ref[0]))
        user32.PostMessageW(hwnd, WM_DESTROY, 0, 0)
        user32.PostQuitMessage(0)

    def wnd_proc(hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_RBUTTONUP:
                show_menu(hwnd)
            elif lparam == WM_LBUTTONDBLCLK:
                webbrowser.open(base_url)
            return 0
        if msg == WM_COMMAND:
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wnd_proc_cb = WNDPROC(wnd_proc)

    # ── Create hidden window + tray icon ──
    hInstance = kernel32.GetModuleHandleW(None)
    class_name = "SalmAlmTray"

    wc = WNDCLASSW()
    wc.lpfnWndProc = wnd_proc_cb
    wc.hInstance = hInstance
    wc.lpszClassName = class_name

    user32.RegisterClassW(ctypes.byref(wc))

    hwnd = user32.CreateWindowExW(0, class_name, "SalmAlm Tray", WS_OVERLAPPED, 0, 0, 0, 0, None, None, hInstance, None)
    hwnd_ref[0] = hwnd

    # Load default icon
    hIcon = user32.LoadImageW(None, IDI_APPLICATION, IMAGE_ICON, 0, 0, LR_SHARED)

    # Create NOTIFYICONDATAW
    nid = NOTIFYICONDATAW()
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAYICON
    nid.hIcon = hIcon
    nid.szTip = f"😈 SalmAlm — AI Gateway (:{port})"
    nid_ref[0] = nid

    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    logger.info(f"[TRAY] System tray icon active (port {port})")

    # ── Message loop ──
    msg = MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
    finally:
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        logger.info("[TRAY] Tray icon removed. Goodbye!")
