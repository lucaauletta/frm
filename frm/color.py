"""Explicit OCIO display pipeline; sources are never inferred from extensions."""
from dataclasses import dataclass
import numpy as np
import PyOpenColorIO as ocio

BUILTIN = "studio-config-v4.0.0_aces-v2.0_ocio-v2.5"


def load_config(path=""):
    return ocio.Config.CreateFromFile(path) if path else ocio.Config.CreateFromBuiltinConfig(BUILTIN)


@dataclass(frozen=True)
class ColorSettings:
    enabled: bool = False
    config: str = ""
    input_space: str = "ACEScg"
    display: str = ""
    view: str = ""
    lut: str = ""
    exposure: float = 0.0


def processor(settings: ColorSettings):
    group = ocio.GroupTransform()
    if settings.exposure:
        gain = 2 ** settings.exposure
        group.appendTransform(ocio.MatrixTransform(matrix=[gain, 0, 0, 0, 0, gain, 0, 0, 0, 0, gain, 0, 0, 0, 0, 1]))
    if settings.enabled:
        config = load_config(settings.config)
        group.appendTransform(ocio.DisplayViewTransform(src=settings.input_space, display=settings.display, view=settings.view))
    else:
        config = ocio.Config.CreateRaw()
    # A viewing LUT is applied AFTER the display transform, in display RGB.
    if settings.lut:
        group.appendTransform(ocio.FileTransform(src=settings.lut, interpolation=ocio.INTERP_BEST))
    return config.getProcessor(group).getDefaultCPUProcessor()


def to_display(rgb, cpu):
    rgb = np.ascontiguousarray(rgb, dtype=np.float32).copy()
    h, w, _ = rgb.shape
    cpu.apply(ocio.PackedImageDesc(rgb, w, h, 3))
    np.nan_to_num(rgb, copy=False, nan=0, posinf=1, neginf=0)
    return np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
