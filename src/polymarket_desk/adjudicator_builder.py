from __future__ import annotations

from pathlib import Path

from polymarket_desk.config import repo_path
from polymarket_desk.loaders import read_text_file


def build_adjudicator_input(packet_path: Path, model_output_a: Path, model_output_b: Path) -> str:
    packet = read_text_file(packet_path)
    output_a = read_text_file(model_output_a)
    output_b = read_text_file(model_output_b)
    instructions = read_text_file(repo_path("prompts", "adjudicator_prompt.md"))

    sections = [
        "# Adjudicator Input Packet",
        "## Adjudicator Instructions",
        instructions.strip(),
        "## Original Research Packet",
        packet.strip(),
        "## Model A Output",
        "```json",
        output_a.strip(),
        "```",
        "## Model B Output",
        "```json",
        output_b.strip(),
        "```",
    ]
    return "\n\n".join(sections).strip() + "\n"


def write_adjudicator_input(
    packet_path: Path, model_output_a: Path, model_output_b: Path, output_path: Path
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_adjudicator_input(packet_path, model_output_a, model_output_b),
        encoding="utf-8",
    )
    return output_path
