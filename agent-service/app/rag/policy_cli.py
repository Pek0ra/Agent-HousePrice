"""Run with python -m app.rag.policy_cli {build,update,inspect,search}."""
from __future__ import annotations

import argparse
import json

from app.config import Settings
from app.rag.policy_index import load_corpus
from app.rag.policy_store import PolicyStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "update", "inspect", "search", "validate"))
    parser.add_argument("query", nargs="?")
    parser.add_argument("--as-of")
    parser.add_argument("--include-unreviewed", action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        _, report = load_corpus()
        result = report
    else:
        store = PolicyStore(Settings().policy_qdrant_location)
        if args.command in {"build", "update"}:
            result = store.build()
        elif args.command == "inspect":
            result = store.inspect()
        else:
            if not args.query:
                parser.error("search requires a query")
            result = store.search(args.query, as_of=args.as_of, include_unreviewed=args.include_unreviewed)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
