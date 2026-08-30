from __future__ import annotations


def add_comment_spacing(text: str) -> str:
    """Insert exactly two blank lines between YAML comment list records."""
    output: list[str] = []
    seen_comment = False
    for line in text.splitlines():
        if line.startswith("  - comment_id:"):
            if seen_comment:
                while output and output[-1] == "":
                    output.pop()
                output.extend(["", ""])
            seen_comment = True
        output.append(line)
    return "\n".join(output) + "\n"
