"""Generate the frozen public node-contract snapshot (F01 / T01).

Development helper only; the authoritative comparison lives in
``tests/test_node_contracts.py``.  Run from the toolkit root:

    python scripts/dump_node_contracts.py            # print a summary
    python scripts/dump_node_contracts.py --check    # diff against the fixture
    python scripts/dump_node_contracts.py --write    # rewrite the fixture

Only run ``--write`` for an intentional, reviewed public-contract change.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from _toolkit_bootstrap import CONTRACT_FIXTURE, collect, load_entry_point  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true", help="rewrite the fixture")
    group.add_argument("--check", action="store_true", help="report drift against the fixture")
    args = parser.parse_args()

    package, _host = load_entry_point()
    contracts = collect(package)

    print(f"nodes: {len(contracts)}")
    for name in sorted(contracts):
        c = contracts[name]
        print(f"  {name:38s} {c['category']!r:26s} outs={len(c['return_types'])}")

    if args.write:
        CONTRACT_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        ordered = {name: contracts[name] for name in sorted(contracts)}
        CONTRACT_FIXTURE.write_text(
            json.dumps(ordered, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {CONTRACT_FIXTURE}")
        return 0

    if args.check:
        expected = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
        drift = [name for name in sorted(set(expected) | set(contracts)) if expected.get(name) != contracts.get(name)]
        if drift:
            print("DRIFT:", ", ".join(drift))
            return 1
        print("contract snapshot is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
