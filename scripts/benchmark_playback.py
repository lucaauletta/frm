"""Measure demand decoding and preview processing without the GUI."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
import statistics
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frm.media import discover
from frm.playback import SourceReader, preview
from frm.color import ColorSettings, processor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--frames", type=int, default=48)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--fast", action="store_true", help="Use bilinear preview scaling")
    args = parser.parse_args()
    results = []
    for mode in ("cpu", "hardware"):
        reader = SourceReader(discover(Path(args.path)), mode, args.width if args.fast else None)
        cpu = processor(ColorSettings())
        decode, transform = [], []
        try:
            for i in range(args.frames):
                start = perf_counter()
                try:
                    rgb = reader.read(i, lambda: False)
                except EOFError:
                    break
                middle = perf_counter()
                preview(rgb, args.width, cpu, args.fast)
                end = perf_counter()
                decode.append((middle-start)*1000); transform.append((end-middle)*1000)
            results.append(dict(requested=mode, actual=reader.backend, fallback=reader.fallback_reason,
                frames=len(decode), first_decode_ms=decode[0] if decode else None,
                median_decode_ms=statistics.median(decode) if decode else None,
                median_preview_ms=statistics.median(transform) if transform else None))
        finally:
            reader.close()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
