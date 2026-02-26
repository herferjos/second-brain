from pathlib import Path


def save_markdown(output_dir: Path, frame_idx: int, markdown_text: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"frame_{frame_idx:04d}.md"
    out_path.write_text(markdown_text, encoding="utf-8")
    print(f"Saved structured markdown: {out_path}")
    return out_path
