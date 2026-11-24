"""Validate the protocol shared by all scans in a survey database."""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

_BSSID = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')


def survey_id(value: str) -> str:
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
        raise ValueError('Survey identifiers must contain 1 to 100 characters')
    return value.strip()


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate survey configuration key: {key}')
        result[key] = value
    return result


def _coordinate(value: object) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Site coordinates must be finite numbers')
    return float(value) or 0.0


@dataclass(frozen=True)
class SurveyConfig:
    sites: Mapping[str, tuple[float, float]]
    targets: Mapping[str, str]
    min_quality: int
    fingerprint: str

    @classmethod
    def load(cls, path: str | Path) -> 'SurveyConfig':
        config = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_keys)
        if not isinstance(config, dict):
            raise ValueError('Survey configuration must be a JSON object')

        min_quality = config.get('min_quality', 0)
        if type(min_quality) is not int or not 0 <= min_quality <= 100:
            raise ValueError('min_quality must be an integer from 0 to 100')

        raw_sites = config.get('sites')
        raw_targets = config.get('targets')
        if not isinstance(raw_sites, dict) or not raw_sites:
            raise ValueError('Register at least one survey site')
        if not isinstance(raw_targets, dict) or not raw_targets:
            raise ValueError('Register at least one authorized target')

        sites = {}
        for raw_site, coordinates in raw_sites.items():
            site = survey_id(raw_site)
            if site in sites or not isinstance(coordinates, dict) or not {'x', 'y'} <= coordinates.keys():
                raise ValueError('Use unique site identifiers and provide x and y coordinates')
            sites[site] = (_coordinate(coordinates['x']), _coordinate(coordinates['y']))

        targets = {}
        for raw_address, raw_alias in raw_targets.items():
            address = raw_address.lower()
            alias = survey_id(raw_alias)
            if not _BSSID.fullmatch(address) or address in targets or alias in targets.values():
                raise ValueError('Use unique target aliases and valid, unique authorized BSSIDs')
            targets[address] = alias

        protocol = {
            'version': 1,
            'sites': sites,
            'targets': targets,
            'min_quality': min_quality,
        }
        encoded = json.dumps(protocol, sort_keys=True, separators=(',', ':'), allow_nan=False)
        fingerprint = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        return cls(MappingProxyType(sites), MappingProxyType(targets), min_quality, fingerprint)
