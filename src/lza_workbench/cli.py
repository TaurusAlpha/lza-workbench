"""Command-line entrypoint for LZA Workbench."""

from __future__ import annotations

import argparse

from lza_workbench import __version__


def build_parser() -> argparse.ArgumentParser:
	"""Create the top-level CLI parser."""
	parser = argparse.ArgumentParser(
		prog="lza",
		description="LZA Workbench CLI",
	)
	parser.add_argument(
		"--version",
		action="version",
		version=f"%(prog)s {__version__}",
	)
	return parser


def main(argv: list[str] | None = None) -> int:
	"""Run the CLI and return a process-style exit code."""
	parser = build_parser()
	parser.parse_args(argv)
	parser.print_help()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
