# Completed Work Log

Concise historical record of completed features, major architecture decisions, and refactors in LZA Workbench.

Work is moved here from `TODO.md` only after implementation, integration, code review, and validation/tests are complete.

---

## 2026-08

### Workspace & Project Setup
- Established Python project structure, package entrypoints (`lza`, `lza-workbench`), repository layout, `uv` configuration, and test suite.
- Defined core declarative architecture (`lza-workspace.yaml`), runtime execution state (`.lza/state.json`), and project documentation workflow.

### Core CLI Workflow Commands
- **`lza init`**: Customer workspace initialization with slug normalization, configuration copy, AWS profile validation, non-interactive execution, and dry-run support.
- **`lza import`**: Adopt existing local `aws-accelerator-config` without modifying customer files, validating layout and generating workspace metadata.
- **`lza installer plan`**: Read installer parameters from `lza-workspace.yaml`, resolve templates, inspect AWS CodeCommit and deployment status, and generate non-mutating action plans.
- **`lza installer deploy`**: Reconcile installer desired state with AWS CloudFormation, execute deployments, track events, and record deployment metadata in `.lza/state.json`.
- **`lza config upload`**: Validate configuration placeholders, package customer `aws-accelerator-config`, upload to S3 configuration sources, and log upload state.
- **`lza config download`**: Download customer configuration from S3 configuration sources with
  `--dry-run`, optional archive extraction, and operational state updates.
- **`lza status`**: Single read-only status dashboard for workspace state, installer details, configuration sources, and pipeline execution metadata.

### AWS Integration Architecture Refactoring
- Centralized boto3 session and client creation into `AwsClientFactory` across all service modules, eliminating direct `boto3` calls outside the factory.

### Modular Refactor Milestones
- Split workspace models, configuration/state persistence, setup, path handling, and readiness
  into the `workspace` package and removed `core/workspace.py`.
- Added shared installer modules for version conversion, configuration validation, parameter
  mapping, template handling, planning, deployment stages, and status calculations.
- Removed persisted AWS access keys, documented external authentication, and added a shared AWS
  execution-context resolver with account checks for AWS-mutating workflows.
- Decomposed installer deployment, rejected unsafe CloudFormation states, and made CodeCommit
  population an explicit manual prerequisite.
- Shared configuration archive, location, and state-update logic between upload and download.
- Added structured status results, fixed pipeline execution-state field usage, and renamed status
  modules to concise public names.
- Moved packaged installer templates, workspace examples, and starter customer configuration into
  the `resources` hierarchy.
- Removed obsolete status compatibility modules and added architecture checks for direct
  Typer/Rich imports and cross-command imports.
