import mmap
import shutil
import subprocess
import sys

cli = shutil.which("codesign")

needle = (
    b"Specifying ':' in the path is deprecated and will not work in a future release"
)
cmd: list[str] | None = None

if cli is not None:
    cmd = ["codesign", "-d"]

    with open(cli, "rb") as fp:
        mm = mmap.mmap(fp.fileno(), 0, prot=mmap.PROT_READ)
        idx = mm.find(needle)
        if idx > -1:
            cmd = cmd + ["--xml", "--entitlements", "-"]
        else:
            cmd = cmd + ["--entitlements", ":-"]
        mm.close()
else:
    print(
        "warning: codesign not found; entitlement extraction is disabled",
        file=sys.stderr,
    )


def xml(path: str):
    if cmd is None:
        return b""

    try:
        return subprocess.check_output(cmd + [path], stderr=subprocess.DEVNULL).strip(
            b"\x00"
        )
    except subprocess.CalledProcessError:
        return b""
