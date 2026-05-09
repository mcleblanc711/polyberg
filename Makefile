.PHONY: install test lint packet clean

install:
	python -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check src tests

packet:
	python -m polyberg.cli build-packet --output reports/generated/packet.md

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache -o -name .mypy_cache \) -prune -exec rm -rf {} +
