import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import package_native
import verify_media_features


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "producer"
        self.output = Path(self.temporary.name) / "package"
        self.spec = Path(self.temporary.name) / "spec.json"
        self.prefix = self.root / "libmpv/arm64-build"
        self.prefix.mkdir(parents=True)
        ffmpeg = self.root / "libmpv/ffmpeg"
        (ffmpeg / "libavcodec").mkdir(parents=True)
        (ffmpeg / "libavformat").mkdir()
        (ffmpeg / "config_components.h").write_text("".join("#define " + name + " 1\n" for name in verify_media_features.REQUIRED))
        (ffmpeg / "libavcodec/codec_list.c").write_text("&ff_libwebp_encoder,\n&ff_libwebp_anim_encoder,\n")
        (ffmpeg / "libavformat/muxer_list.c").write_text("&ff_webp_muxer,\n")
        header = bytearray(64)
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<HH", header, 16, 3, 183)
        (self.prefix / "libmpv.so").write_bytes(header + b"libwebp\0libwebp_anim\0")
        with zipfile.ZipFile(self.prefix / "libmpv_aarch64.zip", "w") as archive:
            archive.write(self.prefix / "libmpv.so", "libmpv.so")
        for base in (self.prefix / "mpv/include/mpv", self.root / "libmpv/mpv/include/mpv"):
            base.mkdir(parents=True)
            for name in package_native.PUBLIC_HEADERS:
                (base / name).write_text("same compiled " + name)
        pc = self.prefix / "mpv/lib/pkgconfig/mpv.pc"
        pc.parent.mkdir(parents=True)
        pc.write_text("Version: 2.5.0\n")
        self.identity = {"origin": "source", "recipe": {"commit": "a" * 40}, "patches": {}}
        lock = {"sdk": {"cli_version": "26.0.0.621"}, "dependencies": []}
        (self.root / "reproducibility").mkdir()
        (self.root / "reproducibility/source-lock.json").write_text(json.dumps(lock))
        features = verify_media_features.verify(self.root)
        self.metadata = {
            **lock, "platform": "ohos-arm64", "builder_commit": "a" * 40, "patches": [], "media_features": features,
            "artifacts": [{"file": name, "sha256": package_native.digest(self.prefix / name)}
                          for name in ("libmpv.so", "libmpv_aarch64.zip")],
        }
        (self.prefix / "manifest.json").write_text(json.dumps(self.metadata))
        (self.prefix / "media-features.json").write_text(json.dumps(features))
        (self.prefix / "sbom.cdx.json").write_text("{}")
        (self.prefix / "SHA256SUMS").write_text("fixture\n")

    def tearDown(self):
        self.temporary.cleanup()

    def export(self):
        return package_native.export(self.root, self.output, self.spec, self.identity)

    def test_exports_matching_public_sdk_without_device_claim(self):
        spec = self.export()
        self.assertEqual(spec["platform"], "ohos")
        self.assertEqual(spec["validation"], {"compiled": True, "runtime": False, "device": False})
        self.assertIn("webp-animated-encode", spec["capabilities"])
        self.assertEqual((self.output / "lib/libmpv.so").read_bytes(), (self.prefix / "libmpv.so").read_bytes())
        self.assertEqual((self.output / spec["layout"]["archive"]).read_bytes(), (self.prefix / "libmpv_aarch64.zip").read_bytes())
        self.assertEqual(json.loads((self.output / "lib/manifest.json").read_text()), self.metadata)
        self.assertTrue((self.output / "include/mpv/client.h").is_file())
        self.assertIn("${pcfiledir}", (self.output / "lib/pkgconfig/mpv.pc").read_text())

    def test_stale_header_is_rejected(self):
        (self.prefix / "mpv/include/mpv/client.h").write_text("old SDK")
        with self.assertRaisesRegex(ValueError, "Installed header"):
            self.export()
        self.assertFalse(self.output.exists())

    def test_old_archive_cannot_receive_new_source_identity(self):
        with zipfile.ZipFile(self.prefix / "libmpv_aarch64.zip", "w") as archive:
            archive.writestr("libmpv.so", "old library")
        with self.assertRaisesRegex(ValueError, "build metadata"):
            self.export()

    def test_builder_commit_and_patch_stack_are_bound(self):
        self.metadata["builder_commit"] = "b" * 40
        (self.prefix / "manifest.json").write_text(json.dumps(self.metadata))
        with self.assertRaisesRegex(ValueError, "producer commit"):
            self.export()

    def test_existing_output_is_never_rewritten(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.export()

    def test_missing_public_api_exports_are_rejected(self):
        with patch.object(package_native, "command", return_value="000000 T mpv_create"):
            with self.assertRaisesRegex(ValueError, "required libmpv exports"):
                package_native.inspect_runtime(self.prefix / "libmpv.so", self.root / "sdk")

    def test_non_sdk_shared_dependency_is_not_silently_omitted(self):
        symbols = "\n".join("000000 T " + name for name in package_native.REQUIRED_SYMBOLS)
        dynamic = "0x1 (NEEDED) Shared library: [libplacebo.so.349]\n"
        with patch.object(package_native, "command", side_effect=[symbols, dynamic]):
            with self.assertRaisesRegex(ValueError, "Unbundled non-SDK"):
                package_native.inspect_runtime(self.prefix / "libmpv.so", self.root / "sdk")


if __name__ == "__main__":
    unittest.main()
