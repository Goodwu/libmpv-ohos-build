import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('verify_media_features', Path(__file__).with_name('verify_media_features.py'))
features = importlib.util.module_from_spec(spec)
spec.loader.exec_module(features)


class NativeFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ffmpeg = self.root / 'libmpv/ffmpeg'
        (self.ffmpeg/'libavcodec').mkdir(parents=True)
        (self.ffmpeg/'libavformat').mkdir()
        (self.ffmpeg/'config_components.h').write_text(''.join('#define '+key+' 1\n' for key in features.REQUIRED))
        (self.ffmpeg/'libavcodec/codec_list.c').write_text('&ff_libwebp_encoder,\n&ff_libwebp_anim_encoder,\n')
        (self.ffmpeg/'libavformat/muxer_list.c').write_text('&ff_webp_muxer,\n')
        self.library = self.root/'libmpv/arm64-build/libmpv.so'
        self.library.parent.mkdir()
        header = bytearray(64); header[:6]=b'\x7fELF\x02\x01'; struct.pack_into('<HH', header, 16, 3, 183)
        self.library.write_bytes(header+b'libwebp\0libwebp_anim\0')

    def tearDown(self): self.temp.cleanup()

    def test_compiled_identity_bound_without_device_claim(self):
        result = features.verify(self.root)
        self.assertEqual(result['libmpv_sha256'], features.digest(self.library.read_bytes()))
        self.assertEqual(result['device_webp_encoding'], 'not-run')

    def test_each_disabled_feature_rejected(self):
        path=self.ffmpeg/'config_components.h'; original=path.read_text()
        for key in features.REQUIRED:
            with self.subTest(feature=key):
                path.write_text(original.replace(key+' 1',key+' 0'))
                with self.assertRaisesRegex(ValueError, 'disabled'): features.verify(self.root)
        path.write_text(original)

    def test_missing_animation_registry_rejected(self):
        (self.ffmpeg/'libavcodec/codec_list.c').write_text('&ff_libwebp_encoder,\n')
        with self.assertRaisesRegex(ValueError, 'registry'): features.verify(self.root)

    def test_missing_muxer_registry_rejected(self):
        (self.ffmpeg/'libavformat/muxer_list.c').write_text('NULL\n')
        with self.assertRaisesRegex(ValueError, 'registry'): features.verify(self.root)

    def test_wrong_architecture_rejected(self):
        data=bytearray(self.library.read_bytes());struct.pack_into('<H',data,18,62);self.library.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'ARM64'): features.verify(self.root)

    def test_stale_final_library_rejected(self):
        self.library.write_bytes(self.library.read_bytes().replace(b'libwebp_anim\0',b'oldlibrary\0'))
        with self.assertRaisesRegex(ValueError, 'omits codec'): features.verify(self.root)


if __name__ == '__main__': unittest.main()
