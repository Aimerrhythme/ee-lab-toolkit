# Tool convention (high-star style)

Every tool lives in `tools/<slug>/` and follows this layout (inspired by popular dual-language / scientific tool repos):

```text
tools/<slug>/
├── README.md           # Purpose, badges line, install, usage, API, FAQ
├── python/
│   ├── __init__.py
│   └── <module>.py     # Core library (importable)
├── matlab/
│   ├── <func>.m        # Core function(s)
│   └── demo_<slug>.m   # Runnable demo
├── examples/
│   ├── data/           # Tiny CSV/MAT samples (synthetic OK)
│   └── run_demo.py     # Python demo entry
└── tests/
    └── test_<slug>.py  # Minimal pytest or assert-based smoke test
```

## README checklist

1. One-paragraph purpose (Chinese OK; keep a one-line English subtitle)
2. Dependencies (Python packages / MATLAB toolboxes)
3. Quick start for **both** runtimes
4. Parameter table
5. Example output (describe figure; optional `assets/` screenshot later)
6. Limitations & teaching disclaimer

## Parity rules

- Same primary function name where practical (`analyze_load` / `analyze_load.m`)
- Same key CLI/script arguments or struct fields
- Example data shared under `examples/data/` when format allows (CSV preferred)

## Daily automation must

- Pick first `todo` in `/themes.md`
- Create a **complete** dual-runtime tool (not a stub README-only)
- Keep code short but runnable
- Update root `README` tool index, `CHANGELOG.md`, mark theme `done`
