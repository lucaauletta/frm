# Changelog

## 0.1.0 — 2026-10-12

Initial preview implementation:

- English Qt desktop interface with drag & drop, numbered sequence discovery, timeline, frame stepping, looping, FPS and fullscreen controls.
- OpenImageIO decoding for DPX, flat EXR, TIFF, JPEG and PNG; FFmpeg/PyAV movie decoding.
- Pinned built-in ACES 2.0 Studio configuration, custom OCIO configs, exposure and viewing LUTs.
- Background preview preparation at 1280, 1920 or 3840 pixels wide, bounded to 8 GiB of temporary disk storage with normal-exit cleanup.
- Synthetic codec/color/cache/lifecycle tests, portable native build tooling and Windows/macOS CI.
- GPL-3.0-only source and English user/contributor documentation.
- Windows packaging isolates DLL discovery from unrelated programs on PATH; frozen-executable smoke tests verify Qt startup, image decoding, ACES and cache cleanup.

Known limits: silent video, 8-bit preview, CPU processing, no HDR/ICC reference output, no VFR timestamp playback, no EXR layer selection, no long-clip sliding cache, unsigned bundles. See README for exact behavior and validation scope.
