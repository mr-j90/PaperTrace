"""Assemble eval/results/*.json into the committed report the README links to."""

import json
from datetime import UTC, datetime
from pathlib import Path

RESULTS = Path("eval/results")


def main() -> None:
    parts = [f"# PaperTrace eval report\n\nGenerated {datetime.now(UTC).date().isoformat()}.\n"]

    manifest = json.loads(Path("eval/ground_truth/manifest.json").read_text())
    parts.append(
        f"Ground truth: {manifest['counts']} · generated {manifest['generated']} against the "
        f"snapshot ending {manifest['snapshot_window_end']} · hand-check: "
        f"{manifest['hand_check']}.\n"
    )

    retrieval = RESULTS / "retrieval.json"
    if retrieval.exists():
        data = json.loads(retrieval.read_text())
        k = data["k"]
        parts.append(f"## Retrieval ladder (n={data['ladder'][0]['n']}, k={k})\n")
        parts.append(f"| mode | hit-rate@{k} | MRR |\n|---|---|---|")
        for rung in data["ladder"]:
            marker = " **(shipped)**" if rung["mode"] == data["best_mode"] else ""
            parts.append(f"| {rung['mode']}{marker} | {rung[f'hit_rate@{k}']} | {rung['mrr']} |")
        parts.append("")

    agent = RESULTS / "agent.json"
    if agent.exists():
        data = json.loads(agent.read_text())
        parts.append(f"## Agent metrics ({data['model']})\n")
        per_set = ", ".join(f"{k} {v['routing_accuracy']}" for k, v in data["per_set"].items())
        parts.append(f"- routing accuracy: **{data['routing_accuracy']}** ({per_set})")
        parts.append(f"- tool-arg exact match: **{data['tool_arg_match']}**")
        parts.append(f"- execution accuracy: **{data['execution_accuracy']}**\n")

    llm = RESULTS / "llm.json"
    if llm.exists():
        data = json.loads(llm.read_text())
        parts.append(f"## LLM grid (judge: {data['judge']})\n")
        parts.append(
            "| cell | faithfulness | citations | completeness | mean |\n|---|---|---|---|---|"
        )
        for cell, s in data["cells"].items():
            marker = " **(shipped)**" if cell == data["best_cell"] else ""
            parts.append(
                f"| {cell}{marker} | {s['faithfulness']} | {s['citation_correctness']} "
                f"| {s['completeness']} | {s['mean']} |"
            )
        parts.append(f"\n> {data['judge_caveat']}\n")

    Path("eval/results/report.md").write_text("\n".join(parts) + "\n")
    print("eval/results/report.md written")


if __name__ == "__main__":
    main()
