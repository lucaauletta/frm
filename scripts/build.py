"""Build a native portable bundle on its target operating system."""
from pathlib import Path
import importlib.metadata as metadata
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frm import __version__


def main():
    env = os.environ.copy()
    if sys.platform == "win32":
        # Do not resolve Qt's system ICU import against unrelated tools on PATH
        # (for example Poppler's incompatible ICU build).
        system = Path(os.environ["SystemRoot"])
        env["PATH"] = os.pathsep.join(map(str, [Path(sys.executable).parent,
            Path(sys.base_prefix), Path(sys.base_prefix) / "DLLs", system / "System32", system]))
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "FRM.spec"], cwd=ROOT, env=env, check=True)
    target = ROOT / "dist" / ("FRM.app/Contents/Resources" if sys.platform == "darwin" else "FRM")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, target / name)
    if (ROOT / "docs").exists():
        shutil.copytree(ROOT / "docs", target / "docs", dirs_exist_ok=True)
    licenses = target / "licenses"
    licenses.mkdir(exist_ok=True)
    inventory = []
    for name in ["PySide6-Essentials", "shiboken6", "numpy", "OpenImageIO", "opencolorio", "av", "reportlab", "pillow", "charset-normalizer"]:
        dist = metadata.distribution(name)
        inventory.append({"name": name, "version": dist.version, "license": dist.metadata.get("License-Expression") or dist.metadata.get("License", "See bundled notices")})
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ("license", "copying", "copyright", "notice")) and dist.locate_file(file).is_file():
                destination = licenses / name / str(file).replace("..", "parent")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dist.locate_file(file), destination)
    (target / "dependency-versions.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    # Ship the exact application source alongside the binary.
    source = target / "source"
    source.mkdir(exist_ok=True)
    for name in ("frm", "scripts", "tests", "docs"):
        if not (ROOT / name).exists():
            continue
        shutil.copytree(ROOT / name, source / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("pyproject.toml", "FRM.spec", "run_frm.py", "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, source / name)
    print(f"Built FRM {__version__} for {platform.system()} {platform.machine()}")


if __name__ == "__main__":
    main()
