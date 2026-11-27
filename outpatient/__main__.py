"""Command-line entry points for setup, evaluation, and the local demo."""

import argparse
import json
import os
from pathlib import Path

from outpatient.data import appointment_summary, connect, import_sources, read_sources, write_sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path("../artifacts"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("fixtures")
    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("--source-url")
    subparsers.add_parser("summary")
    subparsers.add_parser("evaluate-ml")
    evaluate_rag = subparsers.add_parser("evaluate-rag")
    evaluate_rag.add_argument("--model-url", default=os.getenv("MODEL_URL"))
    evaluate_rag.add_argument("--output", type=Path)
    for command, port in [("mock", 8091), ("serve", 8080)]:
        server = subparsers.add_parser(command)
        server.add_argument("--host", default="127.0.0.1")
        server.add_argument("--port", type=int, default=port)
    args = parser.parse_args()
    sources, database = args.work_dir / "sources", args.work_dir / "appointments.sqlite3"
    if args.command == "fixtures":
        write_sources(sources)
    elif args.command == "mock":
        from outpatient.mock import serve

        serve(read_sources(sources), args.host, args.port)
    elif args.command == "serve":
        from outpatient.web import serve

        with connect(database) as connection:
            appointment_summary(connection)
        serve(database, os.getenv("MODEL_URL"), args.host, args.port)
    elif args.command == "evaluate-rag":
        from outpatient.rag import evaluate

        output = json.dumps(evaluate(args.model_url), indent=2)
        if args.output:
            args.output.write_text(output + "\n")
        else:
            print(output)
    else:
        with connect(database) as connection:
            if args.command == "ingest":
                result = import_sources(connection, read_sources(sources, args.source_url))
            elif args.command == "summary":
                result = appointment_summary(connection)
            else:
                from outpatient.model import evaluate

                result = evaluate(connection)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
