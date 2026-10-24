# Contributing

## Add a tool

1. Copy the layout in `docs/tool-convention.md`
2. Implement **both** `python/` and `matlab/` with matching I/O semantics
3. Add `examples/` that run without external proprietary data
4. Add a minimal `tests/` check for the Python path
5. Append a row to the tool index in `README.md` and a line in `CHANGELOG.md`
6. Mark the theme `done` in `themes.md`

## Style

- Python: 3.10+, type hints where helpful, `ruff`-friendly plain code
- MATLAB: R2021b+-friendly, avoid unavailable toolboxes unless declared in the tool README
- Prefer clear names over cleverness; Chinese OK in README, English preferred for function identifiers

## Safety

Do not commit student names, IDs, grades, or non-public utility data.
