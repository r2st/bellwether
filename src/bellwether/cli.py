"""Bellwether CLI — entry point exposed as `bellwether ...` after pip install -e ."""
from __future__ import annotations

import typer

app = typer.Typer(help="Bellwether — supplier risk counter-intel agent.")


@app.command()
def run(
    supplier: str = typer.Option(None, "--supplier", "-s", help="Run one supplier by id."),
    all_suppliers: bool = typer.Option(False, "--all", help="Run the morning batch."),
) -> None:
    """Run a single-supplier or full-batch risk sweep."""
    if not supplier and not all_suppliers:
        raise typer.BadParameter("Pass --supplier <id> or --all.")
    # wiring happens during day-3 of the build plan
    typer.echo(f"(stub) would run: supplier={supplier!r} all={all_suppliers}")


@app.command()
def verify() -> None:
    """Check that all required tokens are set in ../keys/.env."""
    import config  # Bellwether/config.py

    raise typer.Exit(code=0 if config.verify() else 1)


if __name__ == "__main__":
    app()
