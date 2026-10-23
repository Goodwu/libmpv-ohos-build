import hashlib
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

import fetch_sources


class LockedFetchTests(unittest.TestCase):
    def test_git_fetches_exact_commit_when_descriptive_branch_has_advanced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            origin = root / "origin"
            subprocess.run(["git", "init", "--quiet", str(origin)], check=True)
            source = origin / "identity.txt"
            source.write_text("locked")
            subprocess.run(["git", "-C", str(origin), "add", "."], check=True)
            commit = ["git", "-C", str(origin), "-c", "user.name=Fixture", "-c",
                      "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "fixture"]
            subprocess.run(commit, check=True)
            selected = subprocess.check_output(["git", "-C", str(origin), "rev-parse", "HEAD"], text=True).strip()
            source.write_text("new branch tip")
            subprocess.run(["git", "-C", str(origin), "add", "."], check=True)
            subprocess.run(commit, check=True)
            destination = root / "download"
            destination.mkdir()
            fetch_sources.fetch_git({"name": "mpv", "url": str(origin), "commit": selected, "ref": "main"}, destination)
            self.assertEqual((destination / "mpv/identity.txt").read_text(), "locked")
            self.assertEqual(subprocess.check_output(["git", "-C", str(destination / "mpv"), "rev-parse", "HEAD"], text=True).strip(), selected)

    def test_rejects_moving_git_ref(self):
        lock = {"schema": 1, "platform": "ohos-arm64", "dependencies": [
            {"name": "mpv", "url": "https://github.com/example/mpv.git", "commit": "main"}
        ]}
        with self.assertRaisesRegex(ValueError, "complete commit"):
            fetch_sources.validate_lock(lock)

    def test_existing_sources_are_not_relabelled_as_current_inputs(self):
        lock = {"schema": 1, "platform": "ohos-arm64", "dependencies": [
            {"name": name, "url": f"https://github.com/example/{name}.git", "commit": "a" * 40}
            for name in ("mpv", "ffmpeg", "libplacebo", "libwebp")
        ]}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mpv").mkdir()
            with self.assertRaisesRegex(ValueError, "fresh workspace"):
                fetch_sources.fetch(lock, root)

    def test_bad_cached_archive_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source.tar.gz").write_bytes(b"stale")
            with self.assertRaisesRegex(ValueError, "differs from its lock"):
                fetch_sources.fetch_archive({
                    "name": "lua", "archive": "source.tar.gz", "archive_sha256": "0" * 64,
                    "url": "https://example.invalid/source.tar.gz",
                }, root)
            self.assertFalse((root / "lua").exists())

    def test_verified_archive_is_extracted_with_one_source_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as output:
                member = tarfile.TarInfo("source/identity.txt")
                member.size = 6
                output.addfile(member, io.BytesIO(b"locked"))
            fetch_sources.fetch_archive({
                "name": "lua", "archive": archive.name,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "url": "https://example.invalid/source.tar.gz",
            }, root)
            self.assertEqual((root / "lua/identity.txt").read_text(), "locked")


if __name__ == "__main__":
    unittest.main()
