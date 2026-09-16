import copy
import json
import plistlib
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from ipsw.reader import Reader


def load_manifest():
    path = Path(__file__).parent / "fixtures" / "macos-27-26A428.json"
    return json.loads(path.read_text())


EXPECTED_IMAGES = [
    ("Cryptex1,AppOS", "043-70637-685.dmg"),
    ("Cryptex1,RosettaOS", "094-86031-269.dmg"),
    ("Cryptex1,SystemOS", "043-70701-646.dmg.aea"),
    ("OS", "043-70867-635.dmg.aea"),
    ("Cryptex1,SystemOS", "094-72631-342.dmg.aea"),
]


class ReaderTests(unittest.TestCase):
    def read_metadata(self, metadata, name="BuildManifest.plist"):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "firmware.ipsw"
            with ZipFile(archive, "w") as zf:
                zf.writestr(name, plistlib.dumps(metadata, sort_keys=False))
            return Reader(str(archive))

    def test_universal_mac_preserves_both_system_images(self):
        reader = self.read_metadata(load_manifest())
        self.assertEqual(reader.images, EXPECTED_IMAGES)
        self.assertEqual(reader.version, "27.0")
        self.assertEqual(reader.build, "26A428")
        self.assertEqual(reader.devices, ["Mac14,2", "Mac18,5"])

    def test_repeated_install_variants_are_indexed_once(self):
        manifest = load_manifest()
        repeated = copy.deepcopy(manifest["BuildIdentities"])
        for identity in repeated:
            identity["Info"]["Variant"] = "Customer Upgrade Install (IPSW)"
        manifest["BuildIdentities"].extend(repeated)
        self.assertEqual(self.read_metadata(manifest).images, EXPECTED_IMAGES)

    def test_recovery_images_are_excluded(self):
        manifest = load_manifest()
        recovery = copy.deepcopy(manifest["BuildIdentities"][0])
        recovery["Info"]["Variant"] = "macOS Customer Recovery"
        recovery["Manifest"]["OS"]["Info"]["Path"] = "recovery-only.dmg"
        manifest["BuildIdentities"].insert(0, recovery)
        self.assertEqual(self.read_metadata(manifest).images, EXPECTED_IMAGES)

    def test_single_image_ios_manifest(self):
        manifest = {
            "ProductVersion": "18.0",
            "ProductBuildVersion": "22A3354",
            "SupportedProductTypes": ["iPhone16,1"],
            "BuildIdentities": [{
                "Info": {"Variant": "Customer Erase Install (IPSW)"},
                "Manifest": {
                    "OS": {"Info": {"Path": "rootfs.dmg.aea"}},
                    "KernelCache": {"Info": {"Path": "kernelcache"}},
                },
            }],
        }
        self.assertEqual(
            self.read_metadata(manifest).images, [("OS", "rootfs.dmg.aea")]
        )

    def test_legacy_restore_plist(self):
        restore = {
            "ProductVersion": "3.1.3",
            "ProductBuildVersion": "7E18",
            "ProductType": "iPhone1,1",
            "SystemRestoreImages": {"User": "rootfs.dmg"},
        }
        reader = self.read_metadata(restore, "Restore.plist")
        self.assertEqual(reader.images, [("User", "rootfs.dmg")])
        self.assertEqual(reader.devices, ["iPhone1,1"])
