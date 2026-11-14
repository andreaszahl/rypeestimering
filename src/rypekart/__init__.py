"""Rypekart – tetthetskart for lirype på Helgeland.

Each pipeline step is a module runnable with ``uv run python -m rypekart.<steg>``:
omrader -> ar50 -> dtm -> rutenett -> qa.
"""


def main() -> None:
    print("Kjør stegene med: uv run python -m rypekart.<omrader|ar50|dtm|rutenett|qa>")
