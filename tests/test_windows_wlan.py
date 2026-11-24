"""Tests for Windows scan decoding and fresh scan failure handling."""

import ctypes as c

import pytest

from spectraseek import windows_wlan


def bss_buffer(rows):
    offset = windows_wlan._BssList.entries.offset
    entry = windows_wlan._BssEntry
    buffer = c.create_string_buffer(offset + len(rows) * c.sizeof(entry))
    header = (c.c_uint32 * 2).from_buffer(buffer)
    header[:] = len(buffer), len(rows)
    entries = (entry * len(rows)).from_buffer(buffer, offset)
    for raw, (address, quality) in zip(entries, rows):
        raw.bssid[:] = bytes.fromhex(address)
        raw.quality = quality
    return buffer


def test_decode_bss_list_retains_only_strongest_quality():
    buffer = bss_buffer([('0200000000ab', 35), ('0200000000ab', 86), ('0200000000cd', 0)])
    assert windows_wlan._signals(c.addressof(buffer)) == {
        '02:00:00:00:00:ab': 86,
        '02:00:00:00:00:cd': 0,
    }


def test_invalid_bss_list_is_rejected():
    buffer = bss_buffer([('020000000001', 101)])
    with pytest.raises(ValueError, match='quality'):
        windows_wlan._signals(c.addressof(buffer))
    header = (c.c_uint32 * 2).from_buffer(buffer)
    header[1] = 2
    with pytest.raises(ValueError, match='truncated'):
        windows_wlan._signals(c.addressof(buffer))


def test_windows_scan_timeout_unregisters_callback(monkeypatch):
    registrations = []

    class SilentWlan:
        def WlanRegisterNotification(self, _handle, sources, *_args):
            registrations.append(sources)
            return 0

        def WlanScan(self, *_args):
            return 0

    if not hasattr(c, 'WINFUNCTYPE'):
        monkeypatch.setattr(c, 'WINFUNCTYPE', c.CFUNCTYPE, raising=False)
    monkeypatch.setattr(windows_wlan, '_SCAN_TIMEOUT', 0)
    with pytest.raises(RuntimeError, match='did not confirm'):
        windows_wlan._fresh_scan(SilentWlan(), None, windows_wlan._GUID())
    assert registrations == [windows_wlan._ACM, 0]
