from __future__ import annotations

import ctypes

import pytest

import atv_player.ui.x11_window as x11_window


class FakeX11Function:
    def __init__(self, callback) -> None:
        self._callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._callback(*args)


@pytest.mark.parametrize(("enabled", "expected_action"), [(True, 1), (False, 0)])
def test_set_x11_window_above_sends_ewmh_client_message(
    monkeypatch,
    enabled: bool,
    expected_action: int,
) -> None:
    sent_events: list[dict[str, object]] = []
    closed_displays: list[object] = []
    display = ctypes.c_void_p(0x1234)

    def intern_atom(_display, name: bytes, _only_if_exists: bool) -> int:
        return {
            b"_NET_WM_STATE": 100,
            b"_NET_WM_STATE_ABOVE": 101,
        }[name]

    def send_event(_display, destination, propagate, event_mask, event_pointer) -> int:
        client = event_pointer._obj.xclient
        sent_events.append(
            {
                "destination": destination,
                "propagate": propagate,
                "event_mask": event_mask,
                "type": client.type,
                "window": client.window,
                "message_type": client.message_type,
                "format": client.format,
                "data": list(client.data.l),
            }
        )
        return 1

    fake_x11 = type(
        "FakeX11",
        (),
        {
            "XOpenDisplay": FakeX11Function(lambda _name: display),
            "XDefaultRootWindow": FakeX11Function(lambda _display: 99),
            "XInternAtom": FakeX11Function(intern_atom),
            "XSendEvent": FakeX11Function(send_event),
            "XFlush": FakeX11Function(lambda _display: 0),
            "XCloseDisplay": FakeX11Function(
                lambda active_display: closed_displays.append(active_display) or 0
            ),
        },
    )()
    monkeypatch.setattr(
        x11_window.ctypes.util,
        "find_library",
        lambda _name: "libX11.so.6",
    )
    monkeypatch.setattr(x11_window.ctypes, "CDLL", lambda _name: fake_x11)

    x11_window.set_x11_window_above(0xABCDEF, enabled)

    assert sent_events == [
        {
            "destination": 99,
            "propagate": False,
            "event_mask": (1 << 20) | (1 << 19),
            "type": 33,
            "window": 0xABCDEF,
            "message_type": 100,
            "format": 32,
            "data": [expected_action, 101, 0, 1, 0],
        }
    ]
    assert closed_displays == [display]
