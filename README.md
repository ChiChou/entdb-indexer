# entdb-indexer

Crontab workflow to discover and index entitlements from Apple firmware.

Runs daily via GitHub Actions to check for new iOS and macOS versions,
download IPSW firmware files, extract entitlements, and push XML data
to [entdb-data](https://github.com/ChiChou/entdb-data).

OSX (pre-Big Sur) is considered complete and is not checked for updates.

## Structure

- `ipsw-db.py` — Build entitlements database from `.ipsw` firmware files
- `osx-db.py` — Build entitlements database from macOS installer packages
- `cli.py` — CLI tool (`export-xml` to export XML from SQLite)
- `mist.py` — Generate download scripts for macOS installers
- `stages/discover.py` — Discover new firmware versions from source APIs
- `indexer/` — Core library (DB, detection, visitors, entitlements)
- `ipsw/` — IPSW parsing (reader, AEA decryption, wiki keys)
- `osx/` — macOS package handling (hdiutil, cpio, unpack, product names)
- `data/` — Utility scripts for firmware metadata APIs

## Requirements

- Python 3.13+
- macOS system tools: `codesign`, `hdiutil`, `diskutil`
- Optional: `aea`, `vfdecrypt`, `pbzx`, `mist-cli`
- Python dependency: `pyhpke>=0.6.2`

## Related Repositories

| Repository | Description |
|------------|-------------|
| [entdb](https://github.com/ChiChou/entdb) | Web frontend |
| [entdb-data](https://github.com/ChiChou/entdb-data) | Raw entitlement data |

## License

MIT
