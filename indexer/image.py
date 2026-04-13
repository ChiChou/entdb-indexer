import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path

from osx.hdiutil import encrypted as macos_encrypted
from osx.hdiutil import mount_to as macos_mount_to
from osx.hdiutil import unmount as macos_unmount


class ImageBackendError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageProbe:
    encrypted: bool | None


class MountedImage(AbstractContextManager[str]):
    def __init__(self, backend: "ImageBackend", image: str, mount_point: str | None = None):
        self._backend = backend
        self._image = image
        self._requested_mount_point = mount_point
        self._mount_point: str | None = None

    def __enter__(self) -> str:
        self._mount_point = self._backend.mount(self._image, self._requested_mount_point)
        return self._mount_point

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._mount_point is not None:
            self._backend.unmount(self._mount_point)
            self._mount_point = None


class ImageBackend:
    def mount(self, image: str, mount_point: str | None = None) -> str:
        raise NotImplementedError

    def unmount(self, mount_point: str) -> None:
        raise NotImplementedError

    def probe(self, image: str) -> ImageProbe:
        raise NotImplementedError

    def open(self, image: str, mount_point: str | None = None) -> MountedImage:
        return MountedImage(self, image, mount_point)


class MacOSImageBackend(ImageBackend):
    def mount(self, image: str, mount_point: str | None = None) -> str:
        return macos_mount_to(image, mount_point)

    def unmount(self, mount_point: str) -> None:
        macos_unmount(mount_point)

    def probe(self, image: str) -> ImageProbe:
        return ImageProbe(encrypted=macos_encrypted(image))


class LinuxApfsFuseBackend(ImageBackend):
    def __init__(self):
        self._apfs_fuse = shutil.which("apfs-fuse") or shutil.which("apfsfuse")
        self._fusermount = shutil.which("fusermount") or shutil.which("fusermount3")
        self._umount = shutil.which("umount")

        if self._apfs_fuse is None:
            raise ImageBackendError("apfs-fuse is required for Linux disk image mounts")

    def mount(self, image: str, mount_point: str | None = None) -> str:
        target = mount_point or tempfile.mkdtemp(prefix="entdb-apfs-")
        Path(target).mkdir(parents=True, exist_ok=True)

        mount_opts = f"uid={os.getuid()},gid={os.getgid()}"
        cmd = [self._apfs_fuse, "-o", mount_opts, image, target]

        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError as exc:
            if mount_point is None:
                shutil.rmtree(target, ignore_errors=True)
            raise ImageBackendError(f"unable to mount {image}: {exc}") from exc

        return target

    def unmount(self, mount_point: str) -> None:
        if self._fusermount is not None:
            cmd = [self._fusermount, "-u", mount_point]
        elif self._umount is not None:
            cmd = [self._umount, mount_point]
        else:
            raise ImageBackendError("fusermount or umount is required to unmount APFS images")

        try:
            subprocess.check_call(cmd)
        finally:
            self._cleanup_mount_dir(mount_point)

    def probe(self, image: str) -> ImageProbe:
        return ImageProbe(encrypted=None)

    @staticmethod
    def _cleanup_mount_dir(mount_point: str) -> None:
        path = Path(mount_point)
        try:
            path.rmdir()
        except OSError:
            pass


def get_image_backend() -> ImageBackend:
    override = os.environ.get("ENTDB_IMAGE_BACKEND")
    if override == "macos":
        return MacOSImageBackend()
    if override == "linux-apfs":
        return LinuxApfsFuseBackend()

    if sys.platform == "darwin":
        return MacOSImageBackend()

    if sys.platform.startswith("linux"):
        return LinuxApfsFuseBackend()

    raise ImageBackendError(f"unsupported platform: {sys.platform}")