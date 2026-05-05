"""Hatchling build hook that pre-builds the Lit/Vite web frontend.

Runs `npm ci` (or `npm install` if no lockfile) and `npm run build` in `web/`
before hatchling collects files, so the resulting wheel ships with the
compiled static assets in `discocan/server/static/` and end users can install
discocan via pipx without needing Node.js.

Set `DISCOCAN_SKIP_WEB_BUILD=1` to skip — useful for editable installs where
the developer rebuilds the frontend manually with `vite dev`.
"""

import os
import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        if os.environ.get("DISCOCAN_SKIP_WEB_BUILD"):
            return

        root = Path(self.root)
        web_dir = root / "web"
        static_dir = root / "discocan" / "server" / "static"
        index_html = static_dir / "index.html"

        if not (web_dir / "package.json").is_file():
            # No web sources at all — accept any pre-existing static.
            if index_html.is_file():
                return
            raise RuntimeError(
                f"Web sources missing ({web_dir}) and no pre-built static "
                f"assets at {static_dir}. Cannot build."
            )

        npm = shutil.which("npm")
        if npm is None:
            if index_html.is_file():
                self.app.display_warning(
                    "npm not found on PATH — falling back to existing static "
                    f"assets in {static_dir}. Set DISCOCAN_SKIP_WEB_BUILD=1 "
                    "to silence."
                )
                return
            raise RuntimeError(
                "npm not found on PATH and no pre-built static assets exist. "
                "Install Node.js, or set DISCOCAN_SKIP_WEB_BUILD=1 if you "
                f"already populated {static_dir} by other means."
            )

        self.app.display_info(f"Building web frontend in {web_dir}")
        install_cmd = "ci" if (web_dir / "package-lock.json").is_file() else "install"
        subprocess.run([npm, install_cmd], cwd=web_dir, check=True)
        subprocess.run([npm, "run", "build"], cwd=web_dir, check=True)

        if not index_html.is_file():
            raise RuntimeError(f"Web build did not produce {index_html}")
