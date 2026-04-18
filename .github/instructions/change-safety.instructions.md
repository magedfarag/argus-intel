---
applyTo: "**/*"
---

For any file changed after an earlier prompt:
- State which earlier behaviors, keys, rules, or sections must be preserved.
- If removing anything, explain exactly what is removed and why it is safe.
- Prefer targeted edits over full rewrites.
- Summarize added, changed, and removed behavior separately.
- Call out potential regressions before applying destructive edits.

## Batch edit rules (RC-1)
- After any multi-file or multi-replacement batch edit, read each modified section of each file **individually** before proceeding to dependent steps.
- Never place dependent replacements in the same batch. If replacement B references a symbol introduced by replacement A, make them **separate sequential operations** with a verification step between them.

## Full-file replacement rule (RC-3)
- Before any replacement whose `oldString` covers more than 70 % of the file's estimated line count, do a full `read_file` pass first to confirm no additional content (functions, exports, types) will be silently truncated.
- When replacing a file stub that also has import lines already present, verify all imports are carried forward in the new content.

## Behavioral preservation rule (RC-4)
- Before changing any behavior **not explicitly requested** in the user prompt, state the behavioral change in the response and wait for implicit or explicit confirmation. Examples: disabling an existing animation, changing a default position, altering a cache strategy.

## Approval gate (RC-5)
- Any edit to a file that was already touched by an earlier prompt in the same conversation must include a one-line "Preserved from previous edit:" statement naming what must not be overwritten.
