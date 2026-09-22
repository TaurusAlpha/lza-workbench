.PHONY: all repo-map file-architecture docs

REPOMIX_VERSION ?= 1.18.0

all: docs

# LLM-facing repository map: generated on demand and gitignored to avoid commit churn
repo-map:
	npx --yes repomix@$(REPOMIX_VERSION)

# Human-facing repository map: generated from the filesystem and module purpose docstrings
file-architecture:
	python3 scripts/generate_file_architecture.py

docs: repo-map file-architecture
