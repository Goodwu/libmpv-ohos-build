#!/usr/bin/env python3
"""Check compiled WebP support and bind the evidence to the final ARM64 library.

This checks configure output, generated codec/muxer registries and the linked
library, not device encoding or playback. Missing support fails the native build.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ('CONFIG_LIBWEBP_ENCODER', 'CONFIG_LIBWEBP_ANIM_ENCODER', 'CONFIG_WEBP_MUXER')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(root: Path) -> dict:
    source = root / 'libmpv/ffmpeg'
    data = (source / 'config_components.h').read_bytes()
    config = data.decode()
    for name in REQUIRED:
        if not re.search(r'^#define\s+' + name + r'\s+1\s*$', config, re.M):
            raise ValueError('Required compiled feature disabled: ' + name)
    registries = {
        'libavcodec/codec_list.c': ('ff_libwebp_encoder', 'ff_libwebp_anim_encoder'),
        'libavformat/muxer_list.c': ('ff_webp_muxer',),
    }
    registry_hashes = {}
    for path, names in registries.items():
        body = (source / path).read_bytes()
        for name in names:
            if not re.search(rb'&' + name.encode() + rb'\s*,', body):
                raise ValueError('Compiled registry omits ' + name)
        registry_hashes[path] = digest(body)
    library = (root / 'libmpv/arm64-build/libmpv.so').read_bytes()
    if len(library) < 64 or library[:6] != b'\x7fELF\x02\x01' or int.from_bytes(library[16:18], 'little') != 3 or int.from_bytes(library[18:20], 'little') != 183:
        raise ValueError('Expected final ARM64 ELF shared library')
    for marker in (b'libwebp\0', b'libwebp_anim\0'):
        if marker not in library:
            raise ValueError('Final library omits codec identity: ' + marker[:-1].decode())
    return {'schema': 1, 'scope': 'compiled-native-feature-identity-not-device-execution',
            'required_features': {name: True for name in REQUIRED},
            'config_sha256': digest(data), 'registry_sha256': registry_hashes,
            'libmpv_sha256': digest(library), 'device_webp_encoding': 'not-run'}


def main() -> None:
    report = verify(ROOT)
    (ROOT / 'libmpv/arm64-build/media-features.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
