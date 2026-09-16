import importlib.util
import plistlib
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from indexer.db import Writer
from indexer.image import ImageProbe
from tests.test_reader import EXPECTED_IMAGES, load_manifest


spec = importlib.util.spec_from_file_location(
    "ipsw_db", Path(__file__).resolve().parents[1] / "ipsw-db.py"
)
ipsw_db = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ipsw_db)


class PipelineTests(unittest.TestCase):
    def test_every_variant_reaches_database_with_canonical_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            archive = output / "firmware.ipsw"
            with ZipFile(archive, "w") as zf:
                zf.writestr(
                    "BuildManifest.plist",
                    plistlib.dumps(load_manifest(), sort_keys=False),
                )
                for _, path in EXPECTED_IMAGES:
                    zf.writestr(path, path.encode())

            mounted = []
            destinations = []
            writers = []

            class Backend:
                def probe(self, image):
                    return ImageProbe(encrypted=False)

                @contextmanager
                def open(self, image):
                    source = Path(image).read_text()
                    mounted.append(source)
                    destinations.append(image)
                    # A fake mounted volume containing one recognizable Mach-O.
                    with tempfile.TemporaryDirectory(dir=output) as mount:
                        root = Path(mount).resolve()
                        binary = root / "usr" / "libexec" / source.split(".")[0]
                        binary.parent.mkdir(parents=True)
                        binary.write_bytes(b"\xcf\xfa\xed\xfe" + b"\0" * 12)
                        yield str(root)

            def decrypt(cmd, **kwargs):
                self.assertEqual(cmd[:2], ["aea", "decrypt"])
                source = Path(cmd[cmd.index("-i") + 1])
                destination = Path(cmd[cmd.index("-o") + 1])
                shutil.copyfile(source, destination)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            def make_writer(*args):
                writer = Writer(*args)
                writers.append(writer)
                return writer

            def entitlements(path):
                return plistlib.dumps({"test.image": Path(path).name})

            # Capture the real unzip call before mocking AEA's subprocess.run.
            check_call = subprocess.check_call
            try:
                with (
                    patch.object(ipsw_db, "get_image_backend", return_value=Backend()),
                    patch.object(ipsw_db, "get_key", return_value=b"test-key"),
                    patch.object(ipsw_db.subprocess, "run", side_effect=decrypt) as aea,
                    patch.object(ipsw_db.subprocess, "check_call", wraps=check_call) as unzip,
                    patch.object(ipsw_db, "entitlements", side_effect=entitlements),
                    patch.object(ipsw_db, "Writer", side_effect=make_writer),
                ):
                    ipsw_db.build_database(str(archive), output, False)
                self.assertEqual(aea.call_count, 3)
                self.assertEqual(unzip.call_count, 5)
            finally:
                for writer in writers:
                    writer.conn.close()

            self.assertEqual(mounted, [path for _, path in EXPECTED_IMAGES])
            self.assertEqual(len(set(destinations)), 5)
            self.assertTrue(all(not Path(path).exists() for path in destinations))
            self.assertFalse(archive.exists())

            conn = sqlite3.connect(output / "27.0_26A428.db")
            try:
                rows = conn.execute("SELECT path, xml FROM bin").fetchall()
            finally:
                conn.close()
            expected_paths = {
                "/System/Cryptexes/App/usr/libexec/043-70637-685",
                "/System/Cryptexes/Rosetta/usr/libexec/094-86031-269",
                "/System/Cryptexes/OS/usr/libexec/043-70701-646",
                "/usr/libexec/043-70867-635",
                "/System/Cryptexes/OS/usr/libexec/094-72631-342",
            }
            self.assertEqual({path for path, _ in rows}, expected_paths)
            for path, xml in rows:
                self.assertEqual(plistlib.loads(xml)["test.image"], Path(path).name)
