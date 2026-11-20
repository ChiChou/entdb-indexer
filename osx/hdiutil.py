import plistlib
import subprocess
import sys
import time


def hdiutil(*args: str) -> bytes:
    return subprocess.check_output(["hdiutil", *args])


def mount_to(dmg: str, mount: str | None = None) -> str:
    args = ["attach"]

    if mount is not None:
        args += ["-mountpoint", mount]

    args += ["-nobrowse", "-plist", dmg]
    buf = hdiutil(*args)
    plist = plistlib.loads(buf)
    for entry in plist["system-entities"]:
        try:
            return entry["mount-point"]
        except KeyError:
            pass

    raise RuntimeError("not reached")


# A plain detach can hang on DiskArbitration for minutes (seen on GitHub's
# macOS runners right after a big image was walked), so bound each attempt.
DETACH_TIMEOUT = 120
DETACH_ATTEMPTS = 3


def unmount(mount_point: str) -> None:
    """Detach, retrying with -force; raises if every attempt fails."""
    error: Exception | None = None
    for attempt in range(DETACH_ATTEMPTS):
        args = ["hdiutil", "detach", mount_point]
        if attempt > 0:
            args.append("-force")
        try:
            subprocess.run(args, check=True, capture_output=True, timeout=DETACH_TIMEOUT)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            error = e
            stderr = getattr(e, "stderr", None) or b""
            print(
                f"warning: detach {mount_point} failed (attempt {attempt + 1}): "
                f"{stderr.decode(errors='replace').strip() or e}",
                file=sys.stderr,
            )
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"unable to detach {mount_point}") from error


def encrypted(dmg: str) -> bool:
    buf = hdiutil("isencrypted", "-plist", dmg)
    plist = plistlib.loads(buf)
    return plist["encrypted"]


class DiskImage:
    _mp: str | None

    def __init__(self, dmg: str, dest: str | None = None):
        self._dmg = dmg
        self._mp = None
        self._dest = dest

    def __enter__(self):
        mp = mount_to(self._dmg, self._dest)
        self._mp = mp
        return mp

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mp is not None:
            unmount(self._mp)


def ramdisk(size: int) -> str:
    attach_args = ["hdiutil", "attach", "-nomount", ("ram://%d" % size)]
    dev = subprocess.check_output(attach_args).decode().strip()

    format_args = ["diskutil", "erasevolume", "APFS", "RAMDisk", dev]
    subprocess.check_call(format_args)

    info_args = ["hdiutil", "info", "-plist"]
    buf = subprocess.check_output(info_args)
    plist = plistlib.loads(buf)
    for image in plist["images"]:
        entities = image["system-entities"]
        found = any(entity for entity in entities if entity["dev-entry"] == dev)
        if not found:
            continue

        for entity in entities:
            try:
                return entity["mount-point"]
            except KeyError:
                pass

    raise RuntimeError("Unable to find mount point for %s" % dev)


class RamDisk:
    _size: int
    _mp: str | None

    def __init__(self, sz=1048576):
        self._size = sz
        self._mp = None

    def __enter__(self):
        mp = ramdisk(self._size)
        self._mp = mp
        return mp

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._mp is not None:
            unmount(self._mp)
