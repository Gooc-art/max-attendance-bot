from __future__ import annotations

import sys


sys.meta_path = [
    finder
    for finder in sys.meta_path
    if "__editable___max_inspector_bot_0_1_0_finder" not in type(finder).__module__
]

if sys.argv and any("unittest" in arg for arg in sys.argv):
    try:
        from app.db.base import init_db

        init_db()
    except Exception:
        pass
