"""CLI:  python -m app.cli run "<task>"   |   python -m app.cli mcp-check"""
import argparse
import json
import sys

from app.config import get_settings
from app.container import build_container
from app.controllers.schemas import WorkflowResponse
from app.guardrails.input_guards import UserInput
from app.services.workflow_service import SubmitWorkflowCommand


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="run a workflow")
    run.add_argument("task")
    run.add_argument("--context", default="")
    run.add_argument("--max-iterations", type=int, default=None)
    sub.add_parser("mcp-check", help="connect to the MCP server, list tools, invoke one lookup")
    args = p.parse_args(argv)

    if args.cmd == "mcp-check":
        from app.tools.docs_provider import McpDocsProvider, build_docs_provider

        docs = build_docs_provider(get_settings())
        if not isinstance(docs, McpDocsProvider):
            print("MCP is disabled (set MCP_ENABLED=true)")
            return 2
        print("tools:", docs.discover())
        res = docs.fetch("fastapi", "how to declare a POST route")
        print("lookup ok:", res.library_id, f"({len(res.content)} chars)")
        return 0

    container = build_container()
    container.input_guard.enforce(UserInput(args.task, args.context))
    result = container.service.run(SubmitWorkflowCommand(args.task, args.context, max_iterations=args.max_iterations))
    print(json.dumps(WorkflowResponse.from_result(result).model_dump(mode="json"), indent=2))
    return 0 if result.workflow_status.value == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
