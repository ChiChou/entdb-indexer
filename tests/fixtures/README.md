# Firmware manifest fixture

`macos-27-26A428.json` is a reduced `BuildManifest.plist` from
`UniversalMac_27.0_26A428_Restore.ipsw`, the firmware processed by the
[failed job](https://github.com/ChiChou/entdb-indexer/actions/runs/35085307789/job/104758619340).
It retains the disk-image paths and erase-install identities for Mac14,2 and
Mac18,5. The former uses the shared SystemOS image; the latter uses a second,
device-specific SystemOS image. Payloads and unrelated metadata are omitted.

Upstream references:

- [Enumerate distinct SystemOS images](https://github.com/blacktop/ipsw/commit/71fccd1a8781)
- [Scan every variant for firmware database ingestion](https://github.com/blacktop/ipsw/commit/1131d301eeba)

Run the tests with `python -m unittest discover -s tests -v` after installing
the project dependencies. The pipeline test uses real ZIP extraction and SQLite,
with decryption, mounting, and codesign replaced by test doubles.
