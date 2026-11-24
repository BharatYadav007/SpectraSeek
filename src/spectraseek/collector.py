"""Fresh NetworkManager adapter. No monitor mode, packet capture or association."""
from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
import shutil
import subprocess
import sys

_MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', re.I)


@dataclass(frozen=True)
class ScanResult:
    captured_at: datetime
    signals: dict[str, int]  # NetworkManager signal quality, 0–100; not dBm.


def split_fields(line: str) -> list[str]:
    """Decode nmcli terse output, where colons and backslashes are escaped."""
    fields, current = [], []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == '\\':
            escaped = True
        elif char == ':':
            fields.append(''.join(current))
            current = []
        else:
            current.append(char)
    if escaped:
        raise ValueError('Truncated nmcli escape')
    return fields + [''.join(current)]


def parse_scan(text: str) -> dict[str, int]:
    signals = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = split_fields(line)
        if len(fields) != 2 or not _MAC.fullmatch(fields[0]):
            raise ValueError('Unexpected nmcli BSSID/SIGNAL output')
        address, quality = fields[0].lower(), int(fields[1])
        if not 0 <= quality <= 100:
            raise ValueError('Signal quality outside 0–100')
        signals[address] = max(quality, signals.get(address, 0))
    return signals


def _nmcli(*args: str) -> str:
    if not sys.platform.startswith('linux') or not shutil.which('nmcli'):
        raise RuntimeError('Live collection requires Linux with NetworkManager and nmcli')
    result = subprocess.run(['nmcli', '--wait', '30', '--terse', '--escape', 'yes', *args],
                            capture_output=True, text=True, timeout=40,
                            env={**os.environ, 'LC_ALL': 'C'}, check=False)
    if result.returncode:
        raise RuntimeError(f'NetworkManager command failed: {result.stderr.strip()}')
    return result.stdout


def interfaces() -> list[str]:
    return [fields[0] for line in _nmcli('--fields', 'DEVICE,TYPE', 'device', 'status').splitlines()
            if len(fields := split_fields(line)) == 2 and fields[1] == 'wifi']


def scan(interface: str | None = None) -> ScanResult:
    available = interfaces()
    if interface is None:
        if len(available) != 1:
            raise ValueError('Select a Wi-Fi interface explicitly')
        interface = available[0]
    if interface not in available:
        raise ValueError('Selected interface is not a NetworkManager Wi-Fi device')
    output = _nmcli('--fields', 'BSSID,SIGNAL', 'device', 'wifi', 'list',
                    'ifname', interface, '--rescan', 'yes')
    return ScanResult(datetime.now(timezone.utc), parse_scan(output))
