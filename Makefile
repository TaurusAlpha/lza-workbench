.PHONY: all repo-map architecture-diagram docs

REPOMIX_VERSION ?= 1.18.0

all: docs

# LLM-facing repository map: generated on demand and gitignored to avoid commit churn
repo-map:
	npx --yes repomix@$(REPOMIX_VERSION)

# Human-facing architecture diagram: tracked in git so architecture is visible without running tools
architecture-diagram:
	uv run pyreverse -o mmd -p LzaWorkbench -d docs src/lza_workbench
	@test -f docs/packages_LzaWorkbench.mmd || (echo "ERROR: Expected pyreverse output 'docs/packages_LzaWorkbench.mmd' not found" >&2; exit 1)
	mv docs/packages_LzaWorkbench.mmd docs/architecture.mmd
	rm -f docs/classes_LzaWorkbench.mmd

docs: repo-map architecture-diagram
