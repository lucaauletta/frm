# FRM

**Review, simply.** A portable, open-source desktop player for image sequences and movies, with an uncluttered interface and explicit viewing color controls.

FRM is made for artists, editors and post-production teams who want to drop a shot into a viewer, inspect frames and move on.

> **Version 0.1.1 is an early preview, not a validated mastering tool.** It implements real media decoding, ACES/OCIO viewing transforms, LUTs and temporary preview caching. Read the limitations below before using it for production decisions.

## Download and open

Download the package for your computer from [GitHub Releases](https://github.com/lucaauletta/frm/releases).

| Computer | Package | Start |
| --- | --- | --- |
| Windows x64 | `FRM-…-Windows-x64.zip` | Extract the **whole folder**, then double-click `FRM.exe` |
| Mac with Apple Silicon | `FRM-…-macOS-arm64.zip` | Extract, then open `FRM.app` |
| Mac with Intel processor | `FRM-…-macOS-x64.zip` | Extract, then open `FRM.app` |

Packages are produced by the build workflow only when that platform's tests and build succeed. A listed target is not a claim that its release asset is already available. See the [Actions page](https://github.com/lucaauletta/frm/actions) for actual results.

No installer, Python installation, administrator access, account or internet connection is required by the packaged app. Keep all files together; the executable alone is not portable. The app can live on an external drive. Its temporary preview files use the operating system's writable temporary directory.

Early builds are unsigned. Windows SmartScreen or macOS Gatekeeper may ask you to approve opening the app. On macOS, use the normal **Privacy & Security → Open Anyway** flow for a download you trust; do not disable system security globally. macOS builds target macOS 14 or later; Windows builds target Windows 11 x64. Other versions are not validated.

## First shot in three steps

1. **Drop one file.** Drop a movie, a single image, or any numbered frame of a sequence. You can also use **Open media**. A folder containing a single sequence works too.
2. **Press Play or Space.** The first frame appears as soon as it is decoded. A green bar shows cache progress. You can play and scrub the frames already prepared while the rest loads.
3. **Set viewing color if needed.** Open **Viewing color**, enable the OCIO transform, choose the actual source color space, then choose your display and view. Load a viewing LUT if required.

Closing the media or app removes its temporary cache. Original media is read-only and is never moved, rewritten or uploaded. FRM contains no telemetry, network calls or automatic updater.

## Supported media

| Media | Decoder | Notes |
| --- | --- | --- |
| DPX | OpenImageIO | RGB image sequences; choose the correct linear/log input space yourself |
| EXR | OpenImageIO | Flat RGB, including half/float; top-level R/G/B channels only |
| TIFF / TIF | OpenImageIO | First image/subimage only |
| JPEG / JPG, PNG | OpenImageIO | RGB or grayscale; alpha is ignored |
| MOV: ProRes, DNxHD / DNxHR, H.264, H.265 | FFmpeg through PyAV | Decoder availability depends on bundled FFmpeg; see validation below |
| MP4: H.264, H.265 | FFmpeg through PyAV | Video preview only; no audio in this version |

Numbered sequences such as `shot.1001.exr` are found automatically in the same folder. Matching requires the same prefix, extension and numeric padding. Frames sort numerically. Missing frame numbers are reported when caching completes and are **collapsed**, not replaced with black frames. Open one frame when a folder contains multiple sequences. Unnumbered images open as stills.

Synthetic tests exercise DPX, EXR, TIFF, JPEG, PNG, MOV/ProRes, MOV/DNxHD, MOV/DNxHR HQX (10-bit), MP4/H.264 and MP4/H.265. This does not constitute validation of every camera profile, bit depth, chroma mode, container or damaged file.

## Color: explicit, predictable viewing

FRM bundles OpenColorIO and its **ACES 2.0 Studio configuration**, pinned by configuration name. You may load a custom `.ocio` config, including an ACES 1.3 pipeline. Keep any LUTs referenced by a custom config in their expected locations.

The processing order is:

```text
Decoded float RGB → exposure offset → OCIO display/view → optional viewing LUT → 8-bit preview
```

- A new shot starts with **Color: bypass**. No color space is guessed from a filename or extension.
- For an ACEScg render, enable OCIO, select **ACEScg**, choose the display that matches your viewing setup, and select its ACES view.
- For a display-ready JPEG or movie, bypass may be appropriate. Enabling an ACES transform with the wrong input space will give an incorrect image.
- **Load viewing LUT** supports OCIO-readable LUTs, including `.cube`, `.3dl`, `.spi1d`, `.spi3d` and `.csp`. A LUT runs **after** the display transform. For a camera-log-to-display LUT, disable the display transform and ensure the source matches the LUT's expected input.
- Exposure multiplies the input RGB values. Its interpretation in stops is physically meaningful for linear input; it is not a camera-log exposure control.
- Movies are converted from decoded YUV to 16-bit RGB by FFmpeg, then float RGB for OCIO. Embedded HDR/ICC metadata does not automatically configure a viewing transform. This version has no manual YUV matrix/range override.
- Negative and above-one image values survive decoding and reach OCIO. Final display values are clipped to 0–1 and quantized to 8-bit RGB.
- Changing color or preview size rebuilds the cache from the original source and restarts at the first frame.

**The viewer has no HDR/10-bit output, operating-system ICC monitor correction, calibrated video output, alpha compositing, pixel inspector or scopes.** Do not use it as a reference for final color approval. EXR deep data, volumes, multipart/layer selection and multiview are not supported. Only the first part/subimage is read, without applying EXR display-window placement.

## Playback and temporary cache

FRM builds a display-ready preview on a background thread, keeping the controls responsive. The default preview width is **1280 pixels**; 1920 and 3840 are available. Smaller images are not enlarged in the cache. The viewport fits the image to the window without changing its aspect ratio.

- The disk cache is limited to **8 GiB** per open shot and reserves at least **512 MiB** of free space. If either limit is reached, preparation stops with a visible explanation; already cached frames remain playable. Select a smaller preview or a shorter clip.
- Cache files are uncompressed RGB arrays. Fast local storage is recommended. At 1280 × 720 RGB, one frame is about 2.6 MiB; 8 GiB holds roughly two minutes at 24 fps. At 4K it holds much less.
- Each process owns a unique `frm-session-*` directory under the system temp directory. Closing a shot, replacing it or quitting normally deletes that directory after decoding stops. Force quit, a crash or power loss can leave temporary files; after closing all FRM instances, those `frm-session-*` folders may be removed manually. FRM does not delete folders belonging to other instances.
- Playback follows a monotonic clock and may skip preview frames when storage/rendering cannot keep up. Hover over **Play/Pause** to see the skipped-frame count. Frame stepping remains exact for cached frames.
- Playback waits at the prepared boundary while caching continues. Movies use their reported **average frame rate**; variable-frame-rate timestamps, embedded timecode, audio and AV synchronization are not preserved.
- Image sequences default to 24 fps. FPS can be changed from 1 to 120, with three decimal places.

Realtime performance is a target, not a guarantee. Initial decoding is CPU-based, with no hardware video decoding or GPU OCIO path yet. Measure with your actual media, disk and display before relying on a particular resolution or frame rate.

## Controls

| Action | Control |
| --- | --- |
| Open media | Open media / Ctrl+O |
| Play / pause | Space |
| Previous / next cached frame | Left / Right |
| First frame | Home |
| Seek | Timeline |
| Repeat the shot | Loop |
| Fullscreen | F / Fullscreen button |
| Leave fullscreen | Escape |
| Close media and clear cache | Ctrl+W |
| Source path | Hover over the shot name |

## Build from source

For contributors; end users should use portable packages. Use **Python 3.13** and a native Windows or macOS environment. PyInstaller does not cross-compile between these operating systems.

Windows PowerShell:

```powershell
git clone https://github.com/lucaauletta/frm.git
cd frm
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe run_frm.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/build.py
```

macOS Terminal:

```bash
git clone https://github.com/lucaauletta/frm.git
cd frm
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python run_frm.py
.venv/bin/python -m pytest -q
.venv/bin/python scripts/build.py
```

Output: `dist/FRM/FRM.exe` on Windows, `dist/FRM.app` on macOS. Build each Mac architecture on that architecture. Dependencies are pinned in `pyproject.toml`; builds include dependency versions, available third-party notices and the corresponding FRM source.

## Project structure

```text
frm/app.py       Qt interface, transport and application lifecycle
frm/media.py     Sequence discovery and image/movie decoding
frm/color.py     OpenColorIO viewing pipeline
frm/cache.py     Bounded temporary cache
frm/worker.py    Background preview preparation
tests/          Synthetic codec, color, cache and lifecycle tests
scripts/        Native portable build tooling
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development and release steps, [CHANGELOG.md](CHANGELOG.md) for version history and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for dependencies.

## Roadmap

Priorities after the initial preview are production-media validation on both platforms, GPU display transforms, bounded streaming/cache windows for long clips, audio and VFR timing, more precise video color controls, EXR layers/display windows, signing/notarization and measured playback benchmarks. These are planned, **not implemented features**.

## License

FRM is licensed under **GNU GPL version 3 only (`GPL-3.0-only`)**. See [LICENSE](LICENSE).

You may use FRM commercially, study it, change it and share it. If you distribute FRM or a modified version, comply with the GPL, including providing corresponding source and retaining required notices. Using the app does not change the ownership or license of your footage, images or LUTs. Third-party libraries retain their respective licenses. There is no warranty.

Created for Luca Auletta and the open-source post-production community.
