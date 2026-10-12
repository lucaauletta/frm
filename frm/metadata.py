"""Decoder-exposed metadata, read without scanning the whole shot."""
from dataclasses import dataclass, field
from fractions import Fraction
import math
import av
import OpenImageIO as oiio
import numpy as np


@dataclass
class MediaInfo:
    fps: float = 24.0
    fps_exact: str = "24"
    fps_origin: str = "Not reported; using 24 fps"
    total: int = 0
    count_exact: bool = True
    codec: str = ""
    width: int = 0
    height: int = 0
    input_space: str = ""
    color_origin: str = "Color identity unknown; select input color space manually"
    scene_referred: bool = False
    attributes: dict = field(default_factory=dict)


def rate(value):
    try:
        result = Fraction(int(value[0]), int(value[1])) if isinstance(value, (tuple, list)) and len(value) == 2 else Fraction(str(value).strip())
        return result if math.isfinite(float(result)) and 0 < result <= 1000 else None
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None


def printable(value):
    if isinstance(value, bytes):
        return f"Binary data ({len(value):,} bytes)"
    if isinstance(value, (tuple, list)) and len(value) > 128:
        return f"Array ({len(value):,} values; first 16: {value[:16]})"
    return str(value)


def image_color(attrs, config, exr_linear=False):
    """A bare 'linear' hint is insufficient to identify RGB primaries."""
    names = {space.getName().casefold(): space.getName() for space in config.getColorSpaces()}
    aliases = {
        "lin_ap1_scene": "ACEScg", "lin_ap0_scene": "ACES2065-1",
        "lin_rec709_scene": "Linear Rec.709 (sRGB)", "lin_rec709": "Linear Rec.709 (sRGB)",
        "srgb": "sRGB Encoded Rec.709 (sRGB)", "srgb_rec709_scene": "sRGB Encoded Rec.709 (sRGB)",
        "srgb_rec709_display": "sRGB Encoded Rec.709 (sRGB)",
    }
    lowered = {key.casefold(): value for key, value in attrs.items()}
    candidates = []
    for key in ("oiio:colorspace", "colorspace", "aces:colorspace", "ocio:colorspace"):
        text = str(lowered.get(key, "")).strip()
        candidate = names.get(text.casefold()) or aliases.get(text.casefold())
        if candidate:
            candidates.append((candidate, key))
    if lowered.get("acesimagecontainerflag") == 1:
        candidates.append(("ACES2065-1", "acesImageContainerFlag"))
    chroma = lowered.get("chromaticities")
    encoding = str(lowered.get("oiio:colorspace", "")).casefold()
    if chroma is not None and (encoding in ("linear", "scene_linear", "lin_rec709_scene", "acescg", "aces2065-1") or (exr_linear and not encoding)):
        primaries = {
            "ACEScg": [.713, .293, .165, .830, .128, .044, .32168, .33767],
            "ACES2065-1": [.7347, .2653, 0, 1, .0001, -.077, .32168, .33767],
            "Linear Rec.709 (sRGB)": [.64, .33, .30, .60, .15, .06, .3127, .3290],
            "Linear Rec.2020": [.708, .292, .170, .797, .131, .046, .3127, .3290],
        }
        try:
            values = np.asarray(chroma, dtype=float).reshape(-1)
            for name, reference in primaries.items():
                if values.size == 8 and np.allclose(values, reference, atol=0.0001, rtol=0):
                    candidates.append((name, ("EXR linear convention" if not encoding else "linear encoding") + " + chromaticities"))
        except (TypeError, ValueError):
            pass
    identities = {item[0] for item in candidates}
    if len(identities) > 1:
        return "", "Conflicting color metadata: " + ", ".join(sorted(identities)), False
    if not candidates:
        return "", "Color identity ambiguous or absent; select the input space manually", False
    name, origin = candidates[0]
    scene = name in {"ACEScg", "ACES2065-1", "ACEScc", "ACEScct"} or name.startswith("Linear ")
    return name, f"{name} — {origin} (decoder-reported)", scene


def inspect(source, config):
    info = MediaInfo()
    if not source.movie:
        inp = oiio.ImageInput.open(str(source.paths[0]))
        if inp is None:
            raise ValueError(oiio.geterror())
        try:
            spec = inp.spec()
            attrs = {item.name: item.value for item in spec.extra_attribs}
            info.width, info.height, info.total = spec.width, spec.height, len(source.paths)
            info.codec = inp.format_name()
            info.attributes = {k: printable(v) for k, v in attrs.items()}
            info.attributes.update({"Channels": ", ".join(spec.channelnames), "Pixel type": str(spec.format),
                                    "Metadata sample": str(source.paths[0]), "Sequence gaps": str(source.gaps)})
            for key in ("FramesPerSecond", "framesPerSecond", "FrameRate", "frameRate", "dpx:FrameRate", "dpx:TVFrameRate"):
                fps = rate(attrs.get(key))
                if fps:
                    info.fps, info.fps_exact, info.fps_origin = float(fps), str(fps), key
                    break
            info.input_space, info.color_origin, info.scene_referred = image_color(attrs, config, info.codec == "openexr")
        finally:
            inp.close()
        return info
    with av.open(str(source.paths[0])) as container:
        if not container.streams.video:
            raise ValueError("This file has no video stream.")
        stream = container.streams.video[0]
        ctx = stream.codec_context
        info.width, info.height, info.codec = ctx.width, ctx.height, ctx.name
        info.total = stream.frames or 0
        info.count_exact = bool(stream.frames)
        for key, value in (("Average frame rate", stream.average_rate), ("Base frame rate", stream.base_rate),
                           ("Guessed frame rate", stream.guessed_rate)):
            fps = rate(value)
            if fps:
                info.fps, info.fps_exact, info.fps_origin = float(fps), str(fps), key
                break
        info.attributes = {"Container: " + k: printable(v) for k, v in container.metadata.items()}
        info.attributes.update({"Stream: " + k: printable(v) for k, v in stream.metadata.items()})
        for key, value in {"Average frame rate": stream.average_rate, "Base frame rate": stream.base_rate,
                           "Guessed frame rate": stream.guessed_rate, "Time base": stream.time_base,
                           "Duration (stream ticks)": stream.duration, "Start time": stream.start_time,
                           "Pixel format": ctx.format.name if ctx.format else "unknown",
                           "Sample aspect ratio": stream.sample_aspect_ratio}.items():
            info.attributes[key] = printable(value)
        primaries = {1: "BT.709", 2: "unspecified", 9: "BT.2020", 12: "P3-D65"}
        transfer = {1: "BT.709", 2: "unspecified", 8: "linear", 13: "sRGB", 16: "PQ / ST 2084", 18: "HLG"}
        matrices = {0: "RGB", 1: "BT.709", 2: "unspecified", 5: "BT.470BG", 6: "SMPTE 170M", 9: "BT.2020 NCL", 10: "BT.2020 CL"}
        ranges = {0: "unspecified", 1: "limited / video", 2: "full"}
        for key, value, names in [("Color primaries", ctx.color_primaries, primaries),
                                  ("Transfer characteristic", ctx.color_trc, transfer),
                                  ("Matrix coefficients", ctx.colorspace, matrices), ("Color range", ctx.color_range, ranges)]:
            info.attributes[key] = f"{names.get(int(value), 'other')} ({int(value)})"
        p, t = int(ctx.color_primaries), int(ctx.color_trc)
        known = {(1, 1): "Camera Rec.709", (1, 13): "sRGB Encoded Rec.709 (sRGB)",
                 (1, 8): "Linear Rec.709 (sRGB)", (9, 8): "Linear Rec.2020",
                 (9, 16): "Rec.2100-PQ - Display", (9, 18): "Rec.2100-HLG - Display"}
        info.input_space = known.get((p, t), "")
        info.scene_referred = t == 8 and bool(info.input_space)
        if info.input_space:
            info.color_origin = info.input_space + " — video primaries + transfer tags"
            if t in (16, 18):
                info.color_origin += "; HDR detected: choose an SDR view manually"
        else:
            info.color_origin = "Video color tags incomplete or unsupported; no automatic input transform"
    return info
