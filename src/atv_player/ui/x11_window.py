from __future__ import annotations

import ctypes
import ctypes.util

_CLIENT_MESSAGE = 33
_NET_WM_STATE_REMOVE = 0
_NET_WM_STATE_ADD = 1
_SUBSTRUCTURE_NOTIFY_MASK = 1 << 19
_SUBSTRUCTURE_REDIRECT_MASK = 1 << 20


class _XClientMessageData(ctypes.Union):
    _fields_ = [
        ("b", ctypes.c_char * 20),
        ("s", ctypes.c_short * 10),
        ("l", ctypes.c_long * 5),
    ]


class _XClientMessageEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("message_type", ctypes.c_ulong),
        ("format", ctypes.c_int),
        ("data", _XClientMessageData),
    ]


class _XEvent(ctypes.Union):
    _fields_ = [
        ("xclient", _XClientMessageEvent),
        ("pad", ctypes.c_long * 24),
    ]


def _configure_x11_functions(x11) -> None:
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x11.XDefaultRootWindow.restype = ctypes.c_ulong
    x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x11.XInternAtom.restype = ctypes.c_ulong
    x11.XSendEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_int,
        ctypes.c_long,
        ctypes.POINTER(_XEvent),
    ]
    x11.XSendEvent.restype = ctypes.c_int
    x11.XFlush.argtypes = [ctypes.c_void_p]
    x11.XFlush.restype = ctypes.c_int
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
    x11.XCloseDisplay.restype = ctypes.c_int


def set_x11_window_above(window_id: int, enabled: bool) -> None:
    if window_id <= 0:
        raise ValueError("X11 window id must be positive")
    library_name = ctypes.util.find_library("X11")
    if not library_name:
        raise RuntimeError("libX11 is unavailable")
    x11 = ctypes.CDLL(library_name)
    _configure_x11_functions(x11)
    display = x11.XOpenDisplay(None)
    if not display:
        raise RuntimeError("unable to open X11 display")
    try:
        root_window = x11.XDefaultRootWindow(display)
        state_atom = x11.XInternAtom(display, b"_NET_WM_STATE", False)
        above_atom = x11.XInternAtom(display, b"_NET_WM_STATE_ABOVE", False)
        if not root_window or not state_atom or not above_atom:
            raise RuntimeError("unable to resolve X11 always-on-top atoms")

        event = _XEvent()
        event.xclient.type = _CLIENT_MESSAGE
        event.xclient.serial = 0
        event.xclient.send_event = True
        event.xclient.display = (
            display.value if isinstance(display, ctypes.c_void_p) else int(display)
        )
        event.xclient.window = window_id
        event.xclient.message_type = state_atom
        event.xclient.format = 32
        event.xclient.data.l[0] = (
            _NET_WM_STATE_ADD if enabled else _NET_WM_STATE_REMOVE
        )
        event.xclient.data.l[1] = above_atom
        event.xclient.data.l[2] = 0
        event.xclient.data.l[3] = 1
        event.xclient.data.l[4] = 0

        event_mask = _SUBSTRUCTURE_REDIRECT_MASK | _SUBSTRUCTURE_NOTIFY_MASK
        if not x11.XSendEvent(
            display,
            root_window,
            False,
            event_mask,
            ctypes.byref(event),
        ):
            raise RuntimeError("X11 window manager rejected always-on-top request")
        x11.XFlush(display)
    finally:
        x11.XCloseDisplay(display)
