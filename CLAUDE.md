# b3d-validate

Lightweight validation toolkit for build123d CAD shapes. Runs geometry checks (BRepCheck, BOP validity, watertight) and printability checks (overhangs, wall thickness, small features, mesh quality) against OCCT BRep data. Reports are compact and token-efficient, designed for LLM feedback loops.

## Architecture

- `src/b3d_validate/geometry.py` — three-tier geometry validation (null/valid/volume, topology counts, deep BRep/BOP checks)
- `src/b3d_validate/printability.py` — FDM/SLA printability checks (overhangs, wall thickness, small features, optional trimesh mesh checks)
- `src/b3d_validate/__init__.py` — public API: `validate_geometry()`, `validate_printability()`, `full_check()`
- `examples/integration_test.py` — integration test script (requires build123d shapes, not run by pytest)
- `tests/` — unit tests for report dataclasses and formatting (no build123d shapes needed)

## Commands

- `uv run poe check` — run lint, typecheck, security, vulns, then tests
- `uv run poe fix` — auto-format and fix lint issues
- `uv run poe test` — run tests only
- `uv run poe check-all` — run all checks including dead-code and unused-deps

## Stack

uv, ruff (lint/format), ty (type check), pytest, poethepoet (task runner), build123d/OCP (CAD kernel)

## Notes

- OCP (OpenCascade Python bindings) has no type stubs — ty `unresolved-import` is suppressed globally.
- ty is in beta — may produce false positives. Prefer `# ty: ignore[rule]` over blanket suppression.
- Pre-commit hook auto-fixes and restages files. Only blocks on unfixable issues.
- `examples/` is excluded from ruff linting (integration scripts use `from build123d import *` and `print`).
