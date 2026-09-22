# LZA Workbench Roadmap

This file records possible product directions, not approved implementation work. Agents must not
implement roadmap items directly. A direction must first be discussed and translated into concrete
`Future work` or `Planned work` in `TODO.md`.

## Web-First Workspace Lifecycle

Continue developing the local Web interface as the primary interactive experience for workspace
setup, configuration, deployment, status, and diagnostics. Keep the CLI for automation, debugging,
SSH, and advanced use, with both interfaces reusing the same feature-owned behavior.

## Multi-User Operation

Evolve beyond the current local single-user runtime toward authenticated multi-user operation.
Introduce role-based permissions incrementally for capabilities such as read-only access,
administration, and deployment. Authentication, authorization, deployment topology, and security
boundaries require separate design before becoming implementation work.

## Configuration Authoring

Support both manual editing and optional Web-assisted creation and modification of LZA
configuration. Design and implement this incrementally by configuration domain, preserving
unsupported customer content and validating proposed changes before writing them locally.

## Reusable Configuration Patterns

Provide reusable starting points for common customer architectures and feature combinations, such
as centralized or decentralized networking and ingress or egress inspection. During configuration
initialization, let the user select an appropriate starting point and produce a local configuration
that can be reviewed and adapted to the customer's needs.

The source and composition model requires a dedicated design session. Possible approaches include
a small set of bundled complete templates, versioned templates from an external repository, and
composable configuration blocks. Do not commit to Git branches, refs, caching, or a composition
model until that design is complete. Template compatibility with the selected LZA version must be
part of the chosen model.

## AI-Assisted Configuration

Explore advisory AI-assisted authoring of local LZA configuration from natural-language
requirements. Show a proposed diff first, require explicit user approval, and only then update local
configuration files. Configuration synchronization and deployment remain separate explicit user
actions.

Evaluate the capabilities of the AWS-provided LZA MCP server before choosing an integration
architecture. MCP is a possible implementation mechanism, not the goal itself.
