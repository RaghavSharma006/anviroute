"""Build the downloadable Windows bundle after creating a wheel in dist/."""

import hashlib
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build():
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "anviroute/__init__.py").read_text()).group(1)
    wheel = ROOT / "dist" / f"anviroute-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit("Build the wheel first: python -m pip wheel --no-deps --wheel-dir dist .")
    names = ["pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md",
             ".gitignore", ".gitattributes", "anviroute.cmd", "install.cmd", "install.ps1", "requirements-dev.txt"]
    files = [ROOT / name for name in names]
    for folder in ("anviroute", "kagglelink", "tests", "docs", "examples", ".github", "scripts"):
        files.extend(path for path in (ROOT / folder).rglob("*") if path.is_file()
                     and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo"))
    files.append(wheel)
    archive = ROOT / "dist/AnviRoute-Windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(files):
            bundle.write(path, Path("AnviRoute") / path.relative_to(ROOT))
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert "AnviRoute/install.cmd" in bundle.namelist()
        assert not any("token" == Path(name).name or "WORK_CHECKPOINT" in name for name in bundle.namelist())
    checksums = ROOT / "dist/SHA256SUMS.txt"
    checksums.write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
                                 for path in (archive, wheel)), encoding="utf-8")
    print(f"Built {archive.name} ({len(files)} files) and SHA256SUMS.txt")


if __name__ == "__main__":
    build()
