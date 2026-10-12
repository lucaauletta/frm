# Contributing to FRM

Keep the experience simple. Prefer one obvious action over another preferences panel, and never silently guess color-critical settings.

## Local development

Follow the source setup in the README. Run `python -m pytest -q` before submitting changes. Tests generate their own small fixtures; never commit client footage, proprietary LUTs, secrets or large media files.

The UI belongs on the Qt main thread. Decoding and OCIO preparation belong in workers. Every worker must support cancellation. Cache deletion must happen only after the writer has stopped and only for a directory created by that cache instance. Preserve float image data until the display conversion. Never add source-image writes to the viewing path.

Report bugs through GitHub Issues with OS/architecture, FRM version, format/codec, source dimensions, selected color settings, expected behavior and the error text. Include a small redistributable sample when possible. For performance reports include storage type and whether the shot was fully cached.

## Releases

1. Update `frm/__init__.py`, `pyproject.toml`, the macOS version in `FRM.spec`, and `CHANGELOG.md` together.
2. Run the automated tests and a native portable build. Check drag & drop, play/pause, seek, LUT/ACES, replacement during decoding and cache cleanup. Verify representative production media separately from synthetic tests.
3. Commit and push the version to `main`. Tag the tested commit as `vX.Y.Z`, then push that tag.
4. The native-build workflow tests and builds Windows x64, macOS arm64 and macOS x64. A tagged build publishes a prerelease only after all three targets succeed.
5. Review artifacts, dependency licenses and platform behavior before promoting a prerelease. Unsigned builds and known limitations must remain clearly labeled.

Do not commit build products. Do not rewrite published tags or force-push shared history. Do not call a platform tested merely because a build configuration exists. Code contributions are licensed under GPL-3.0-only; contributors retain copyright in their work.
