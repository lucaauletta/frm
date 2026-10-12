"""Media discovery and float decoding. No source files are modified."""
from dataclasses import dataclass
from pathlib import Path
import re

import av
import numpy as np
import OpenImageIO as oiio

IMAGES = {".dpx", ".exr", ".tif", ".tiff", ".jpg", ".jpeg", ".png"}
MOVIES = {".mov", ".mp4", ".m4v"}
NUMBER = re.compile(r"^(.*?)(\d+)$")
MAX_PIXELS = 100_000_000


@dataclass(frozen=True)
class Source:
    paths: tuple[Path, ...]
    movie: bool = False
    gaps: int = 0

    @property
    def name(self):
        return self.paths[0].name


def discover(path: Path) -> Source:
    path = path.resolve()
    if path.is_dir():
        candidates = sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGES and p.is_file())
        if not candidates:
            raise ValueError("This folder contains no supported images.")
        groups = {sequence_key(p) for p in candidates}
        if len(groups) != 1:
            raise ValueError("This folder contains multiple sequences. Drop one frame of the sequence you want.")
        path = candidates[0]
    if not path.is_file():
        raise ValueError("The file is missing or cannot be read.")
    if path.suffix.lower() in MOVIES:
        return Source((path,), movie=True)
    if path.suffix.lower() not in IMAGES:
        raise ValueError("Unsupported file. Open DPX, EXR, TIFF, JPEG, PNG, MOV or MP4.")
    match = NUMBER.match(path.stem)
    if not match:
        return Source((path,))
    key = sequence_key(path)
    frames = sorted((p for p in path.parent.iterdir() if p.is_file() and sequence_key(p) == key),
                    key=lambda p: int(NUMBER.match(p.stem)[2]))
    nums = [int(NUMBER.match(p.stem)[2]) for p in frames]
    return Source(tuple(frames), gaps=nums[-1] - nums[0] + 1 - len(nums))


def sequence_key(path: Path):
    match = NUMBER.match(path.stem)
    return (match[1], len(match[2]), path.suffix.lower()) if match else (path.stem, 0, path.suffix.lower())


def read_image(path: Path):
    inp = oiio.ImageInput.open(str(path))
    if inp is None:
        raise ValueError(f"Cannot decode {path.name}: {oiio.geterror()}")
    try:
        spec = inp.spec()
        if spec.deep or spec.depth > 1 or spec.width * spec.height > MAX_PIXELS:
            raise ValueError("Deep, volume or images above 100 megapixels are not supported.")
        names = list(spec.channelnames)
        if all(c in names for c in ("R", "G", "B")):
            channels = [names.index(c) for c in ("R", "G", "B")]
        elif spec.nchannels in (1, 2):
            channels = [0, 0, 0]
        elif spec.nchannels == 3:
            channels = [0, 1, 2]
        else:
            raise ValueError("No top-level RGB channels found. Export a flat RGB beauty image.")
        data = inp.read_image(format=oiio.FLOAT)
        if data is None:
            raise ValueError(inp.geterror())
        return np.ascontiguousarray(data[:, :, channels], dtype=np.float32)
    finally:
        inp.close()


def frames(source: Source, stop):
    if not source.movie:
        for path in source.paths:
            if stop():
                return
            yield read_image(path)
        return
    with av.open(str(source.paths[0])) as container:
        if not container.streams.video:
            raise ValueError("This file has no video stream.")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if stream.width * stream.height > MAX_PIXELS:
            raise ValueError("Video exceeds the 100 megapixel safety limit.")
        for frame in container.decode(stream):
            if stop():
                return
            # Keep 16-bit precision until OCIO; no implicit transfer-function conversion.
            yield frame.to_ndarray(format="rgb48le").astype(np.float32) / 65535.0


def probe(source: Source):
    if not source.movie:
        return 24.0, len(source.paths), "Image sequence" if len(source.paths) > 1 else "Still image"
    with av.open(str(source.paths[0])) as container:
        if not container.streams.video:
            raise ValueError("This file has no video stream.")
        stream = container.streams.video[0]
        return float(stream.average_rate or 24), stream.frames or 0, stream.codec_context.name
