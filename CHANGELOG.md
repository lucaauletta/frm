# Changelog

## 0.3.0

- Windows single-file portable executable and upgrade-aware per-user installer.
- Optional GitHub release checks.
- Linux x64 portable build on Ubuntu 24.04.
- Luca Auletta publisher metadata and embedded source/notices.

## 0.2.0 — 2026-10-12

- FRM becomes a player and review workspace with a compact viewer-focused interface.
- Direct on-demand reading: no full-shot cache preparation before playback; optional RAM or disk LRU cache fills after frames are displayed. The configured cache budget is shared by A/B.
- Decoder metadata inspector, automatic rational frame rates, explicit input color identification and conservative ACES setup for recognized linear sources. Unknown or conflicting metadata remains visible and is not guessed.
- Two-version A/B viewing, side-by-side comparison and draggable wipe. Signed frame offset uses B = A + offset; out-of-range B frames remain blank.
- Frame-bound freehand paint, brush color/width, undo, per-frame text notes and a review note list.
- All annotated frames export as PNG/JPG plus a notes manifest, or as a paginated PDF report.
- Save/open `.frmreview` documents with paint, text, preview snapshots, source references, color settings and A/B alignment. Cache remains separate and disposable.
- Offline portable smoke checks now exercise direct/RAM/disk reading, cache cleanup, A/B, PDF export and review-document roundtrip.

Known limits: frame-based A/B alignment does not resample differing source FPS; uncached backward movie seeks restart exact-index decoding; metadata comes from the first image/first video stream; exported frames are display previews, not source-resolution masters. Force termination may leave disk cache directories. Saved review documents and exports are intentionally permanent.

## 0.1.1 — 2026-10-12

- Fix startup with the forced English locale using a portable Qt locale identifier.
- Exercise application configuration in the GUI tests as well as the frozen smoke test.
- First downloadable preview release; the v0.1.0 release build was blocked by its startup smoke check.

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
