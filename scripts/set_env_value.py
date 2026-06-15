from __future__ import annotations

import sys
from pathlib import Path


def set_env_value(env_path: Path, key: str, value: str) -> int:
    lines: list[str] = []
    found = False
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updated: list[str] = []
    for line in lines:
        if line.startswith(f"{key}="):
            updated.append(f"{key}={value}")
            found = True
        else:
            updated.append(line)

    if not found:
        updated.append(f"{key}={value}")

    env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: set_env_value.py <env_file> <key> <value>", file=sys.stderr)
        return 1

    env_path = Path(sys.argv[1])
    key = sys.argv[2]
    value = sys.argv[3]
    return set_env_value(env_path, key, value)


if __name__ == "__main__":
    raise SystemExit(main())
