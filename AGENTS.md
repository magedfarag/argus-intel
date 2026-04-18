# Agent instructions

This repository uses an external Copilot optimizer.

Rules:
1. Default to read-first behavior.
2. Before any write, summarize intended files and why.
3. Product code changes need explicit approval.
4. Copilot add-in file changes need approval artifacts and must remain reversible.
5. After approved actions, document what changed and how it was verified.
6. For files already changed in earlier prompts, list preserved behavior before applying a new edit.
