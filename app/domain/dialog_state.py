from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class UserDialogState:
    flow: str
    step: str
    data: Dict[str, str] = field(default_factory=dict)
