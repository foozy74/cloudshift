---
applyTo: "coriolis/providers/**/*.py"
description: "Use when implementing or modifying Coriolis providers, endpoint provider capabilities, export/import provider code, or provider-specific workflows."
---

# Coriolis Provider Instructions

- Keep provider changes isolated to coriolis/providers/ unless an explicit cross-module contract requires updates.
- Preserve provider interface compatibility with existing base classes and capability methods.
- Do not bypass orchestration layers by adding direct cross-service shortcuts.
- Reuse patterns from sibling providers before introducing new abstractions.
- If provider behavior changes output structures or required fields:
  - Update related schemas and validation logic in the same change.
  - Update policy and tests that validate provider-facing behavior.
- Keep credentials and secrets handling consistent with existing abstractions; never hardcode credentials.
- Prefer additive, backward-compatible changes to provider connection_info and environment fields.
- For new provider options, follow existing configuration registration patterns and include safe defaults.
- Validate provider-related changes with the smallest relevant tox run first, then broaden as needed.
