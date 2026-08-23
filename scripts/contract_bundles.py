"""Backward-compatible imports for the installable Runtime bundle module.

The repository validator historically imported ``scripts.contract_bundles``.
Keep that public surface while the implementation lives in the production
``skillgraph_runtime`` package.  The source-tree bootstrap is deterministic and
only points at this repository's resolved ``src`` directory so direct script
execution continues to work before an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path


_SOURCE_ROOT = (Path(__file__).resolve().parents[1] / "src").resolve()
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from skillgraph_runtime.bundles import *  # noqa: F401,F403,E402
