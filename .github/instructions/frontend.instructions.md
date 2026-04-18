---
applyTo: "**/*.{ts,tsx,js,jsx,vue,css,scss,html}"
---

For frontend changes:
- Keep prompts compact and tied to one flow or screen at a time.
- Preserve existing design system and accessibility patterns.
- Explain state, validation, and API contract impact when behavior changes.
- Prefer small patches over broad refactors unless requested.

## MapLibre / map component rules (RC-2 / P-8)
- Apply event handlers **symmetrically**: when adding or changing a handler on `MapView`, always apply the equivalent change to `GlobeView`, and vice versa. Check both before calling the task complete.
- After editing any MapLibre map component, verify that **both** the map init block (center/zoom restore) and the event listener (e.g., `moveend` persist) are present and correct.
- Do not skip or bypass an existing entry animation or UX flow without explicitly stating the behavioral change in the response before applying it.
- localStorage keys for map state must use the `geoint:` namespace prefix. Document any new key added (key name, value shape, when written, when read).

## React hook rules
- Before replacing a hook file, read the full file first. Hooks often export multiple functions; replacing only the visible top portion silently drops lower exports.
- When adding a cache layer to a server-backed hook (e.g., React Query), prefer `placeholderData` or a wrapper hook over replacing the core `useQuery` call entirely.
