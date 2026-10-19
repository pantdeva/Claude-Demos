"""Load settings from sfa.env (next to the app) into the environment.

Lines are KEY=value; blank lines and # comments are ignored. A variable that is already
set in the environment is left alone, so the file only fills gaps. sfa.env is in
.gitignore: keys stay on this computer.
"""

from __future__ import annotations

import os

from .config import ROOT


def load_env(path=None) -> list[str]:
    f = path or ROOT / "sfa.env"
    loaded = []
    if not f.exists():
        return loaded
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and v and not os.environ.get(k):
            os.environ[k] = v
            loaded.append(k)
    return loaded
