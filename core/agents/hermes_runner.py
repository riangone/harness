"""CLI runner for HermesAgent"""

import asyncio
import argparse
import sys

from core.agents.hermes import HermesAgent


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--tools", default="all")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--work-dir", default=".")
    args = parser.parse_args()

    tools = None if args.tools == "all" else args.tools.split(',')
    agent = HermesAgent(tools=tools, max_react_steps=args.max_steps, work_dir=args.work_dir)
    result = await agent.run(task=args.prompt)

    print(f"[HermesAgent] {'success' if result.success else 'failure'}")
    if result.final_answer:
        print(f"[Answer] {result.final_answer}")
    if result.artifacts:
        print(f"[Artifacts] {', '.join(result.artifacts)}")
    if result.error:
        print(f"[Error] {result.error}", file=sys.stderr)

    for step in result.react_steps:
        print(f"\n[Step {step.step_num}] {step.thought[:100]}")
        for tc in step.tool_calls:
            print(f"  -> tool: {tc.get('name')} params={tc.get('params')}")
        for obs in step.observations:
            status = '✓' if obs.success else '✗'
            print(f"  {status} result: {str(obs.output)[:200]}")

    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    asyncio.run(main())
