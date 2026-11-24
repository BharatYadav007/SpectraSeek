"""Read WLAN signal quality through Windows Native Wi-Fi.

The adapter reads a fresh OS scan. It uses only BSSID and link quality
and leaves association and network configuration to Windows.
"""

from collections import Counter
from contextlib import contextmanager
import ctypes as c
from datetime import datetime, timezone
from threading import Event
from uuid import UUID

from .collector import ScanResult

_DWORD = c.c_uint32
_POINTER = c.c_void_p
_GUID = c.c_ubyte * 16
_ACM = 8
_SCAN_COMPLETE = 7
_SCAN_FAILED = 8
_SCAN_TIMEOUT = 12


class _Interface(c.Structure):
    _fields_ = [
        ('guid', _GUID), ('description', c.c_uint16 * 256), ('state', _DWORD),
    ]


class _Notification(c.Structure):
    _fields_ = [
        ('source', _DWORD), ('code', _DWORD), ('guid', _GUID),
        ('data_size', _DWORD), ('data', _POINTER),
    ]


class _BssEntry(c.Structure):
    _fields_ = [
        ('ssid_length', _DWORD), ('ssid', c.c_ubyte * 32),
        ('phy_id', _DWORD), ('bssid', c.c_ubyte * 6),
        ('bss_type', _DWORD), ('phy_type', _DWORD),
        ('rssi', c.c_int32), ('quality', _DWORD),
        ('in_reg_domain', c.c_ubyte), ('beacon_period', c.c_uint16),
        ('timestamp', c.c_uint64), ('host_timestamp', c.c_uint64),
        ('capabilities', c.c_uint16), ('frequency', _DWORD),
        ('rate_set_length', _DWORD), ('rates', c.c_uint16 * 126),
        ('ie_offset', _DWORD), ('ie_size', _DWORD),
    ]


class _BssList(c.Structure):
    _fields_ = [('size', _DWORD), ('count', _DWORD), ('entries', _BssEntry * 1)]


def _api():
    api = c.WinDLL('wlanapi')
    guid_ptr = c.POINTER(_GUID)
    out_pointer = c.POINTER(_POINTER)
    signatures = {
        'WlanOpenHandle': [_DWORD, _POINTER, c.POINTER(_DWORD), out_pointer],
        'WlanCloseHandle': [_POINTER, _POINTER],
        'WlanEnumInterfaces': [_POINTER, _POINTER, out_pointer],
        'WlanRegisterNotification': [
            _POINTER, _DWORD, c.c_int, _POINTER, _POINTER, _POINTER, c.POINTER(_DWORD),
        ],
        'WlanScan': [_POINTER, guid_ptr, _POINTER, _POINTER, _POINTER],
        'WlanGetNetworkBssList': [
            _POINTER, guid_ptr, _POINTER, _DWORD, c.c_int, _POINTER, out_pointer,
        ],
        'WlanFreeMemory': [_POINTER],
    }
    for name, args in signatures.items():
        function = getattr(api, name)
        function.argtypes = args
        function.restype = None if name == 'WlanFreeMemory' else _DWORD
    return api


def _check(code, operation):
    if code == 5:
        raise RuntimeError(
            f'{operation} was denied. Check Windows Location settings and location access for desktop apps.'
        )
    if code:
        raise RuntimeError(f'{operation} failed with Windows error {code}')


@contextmanager
def _handle():
    api = _api()
    handle = _POINTER()
    version = _DWORD()
    _check(api.WlanOpenHandle(2, None, c.byref(version), c.byref(handle)), 'WlanOpenHandle')
    try:
        yield api, handle
    finally:
        api.WlanCloseHandle(handle, None)


def _radios(api, handle):
    buffer = _POINTER()
    _check(api.WlanEnumInterfaces(handle, None, c.byref(buffer)), 'WlanEnumInterfaces')
    try:
        count = _DWORD.from_address(buffer.value).value
        entries = (_Interface * count).from_address(buffer.value + 2 * c.sizeof(_DWORD))
        radios = []
        for entry in entries:
            if entry.state == 0:  # wlan_interface_state_not_ready
                continue
            guid = bytes(entry.guid)
            description = bytes(entry.description).decode('utf-16-le').split('\0', 1)[0].strip()
            radios.append((description or str(UUID(bytes_le=guid)), guid))
    finally:
        api.WlanFreeMemory(buffer)

    counts = Counter(name.casefold() for name, _ in radios)
    return {
        name if counts[name.casefold()] == 1 else f'{name} [{UUID(bytes_le=guid)}]': guid
        for name, guid in radios
    }


def interfaces() -> list[str]:
    with _handle() as (api, handle):
        return list(_radios(api, handle))


def _fresh_scan(api, handle, guid):
    ready = Event()
    outcome = None
    expected_guid = bytes(guid)
    callback_type = c.WINFUNCTYPE(None, c.POINTER(_Notification), _POINTER)

    @callback_type
    def on_notification(payload, _context):
        nonlocal outcome
        event = payload.contents
        if (
            event.source == _ACM
            and bytes(event.guid) == expected_guid
            and event.code in (_SCAN_COMPLETE, _SCAN_FAILED)
            and outcome is None
        ):
            outcome = event.code
            ready.set()

    _check(
        api.WlanRegisterNotification(handle, _ACM, False, c.cast(on_notification, _POINTER), None, None, None),
        'WlanRegisterNotification',
    )
    try:
        _check(api.WlanScan(handle, c.byref(guid), None, None, None), 'WlanScan')
        if not ready.wait(_SCAN_TIMEOUT):
            raise RuntimeError('Windows did not confirm Wi-Fi scan completion')
        if outcome == _SCAN_FAILED:
            raise RuntimeError('Windows reported a Wi-Fi scan failure')
    finally:
        api.WlanRegisterNotification(handle, 0, False, None, None, None, None)


def _signals(address):
    size, count = (_DWORD * 2).from_address(address)
    start = _BssList.entries.offset
    if size < start or count > (size - start) // c.sizeof(_BssEntry):
        raise ValueError('Windows returned a truncated Wi-Fi scan result')
    entries = (_BssEntry * count).from_address(address + start)
    signals = {}
    for entry in entries:
        quality = entry.quality
        if quality > 100:
            raise ValueError('Windows link quality outside 0–100')
        bssid = bytes(entry.bssid).hex(':')
        signals[bssid] = max(quality, signals.get(bssid, 0))
    return signals


def scan(interface: str | None = None) -> ScanResult:
    with _handle() as (api, handle):
        radios = _radios(api, handle)
        if interface is None:
            if len(radios) != 1:
                raise ValueError('Select a Windows Wi-Fi interface explicitly')
            guid = _GUID.from_buffer_copy(next(iter(radios.values())))
        else:
            selected = next((guid for name, guid in radios.items() if name.casefold() == interface.casefold()), None)
            if selected is None:
                raise ValueError('Selected interface is not a Windows Wi-Fi device')
            guid = _GUID.from_buffer_copy(selected)

        _fresh_scan(api, handle, guid)
        buffer = _POINTER()
        _check(
            api.WlanGetNetworkBssList(handle, c.byref(guid), None, 3, False, None, c.byref(buffer)),
            'WlanGetNetworkBssList',
        )
        try:
            return ScanResult(datetime.now(timezone.utc), _signals(buffer.value), backend='windows-wlan')
        finally:
            api.WlanFreeMemory(buffer)
