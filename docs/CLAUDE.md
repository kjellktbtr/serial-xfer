# Project Wiki: serial-xfer

Self-organizing knowledge base for this project. Grown and maintained by the LLM agent as the project is worked on. All paths below are relative to the repository root.

## Structure

- `docs/raw/` — Immutable ingested external documents (specs, papers, exported docs). Never modify files here.
- `docs/wiki/` — LLM-generated and maintained markdown pages.
- `docs/wiki/index.md` — Master content catalog. Update on every operation.
- `docs/wiki/log.md` — Append-only operation log (one line per operation, dated).
- `docs/outputs/` — Generated reports, presentations, lint results.
- `docs/improvements.md` — Checklist of observed issues and out-of-scope items (see CLAUDE.md section 5).

## Bootstrap

The project template ships without these directories — their absence means "not bootstrapped yet", not an error.

On the first wiki operation in a new project:
1. Create `docs/wiki/index.md` and `docs/wiki/log.md`.
2. Create `docs/raw/` and `docs/outputs/` only when first needed.
3. Update the first line of this file to describe the project's wiki.

## Page Types and Conventions

Every wiki page must have YAML frontmatter:

    ---
    title: Page Title
    type: concept | entity | source-summary | comparison | decision | code-map
    sources:
      - docs/raw/specs/filename.md
      - src/module/file.py
    related:
      - "[[related-concept]]"
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    confidence: high | medium | low
    ---

Page types:
- `concept` — An idea, mechanism, or domain notion and how it works.
- `entity` — A concrete thing: a library, service, person, tool, dataset.
- `source-summary` — Key takeaways from one ingested document in `docs/raw/`.
- `comparison` — Alternatives weighed against each other.
- `decision` — A settled choice: what was decided, why, and which alternatives were rejected.
- `code-map` — Orientation for a subsystem: how it hangs together, entry points, key files, invariants.

### Sources

- `docs/raw/` holds ingested *external* documents only. Source code is referenced in place (e.g. `src/foo.py:42`), never copied into `docs/raw/`.
- Frontmatter `sources:` may list `docs/raw/...` paths, code paths, or both.
- When stating facts in a page, back them with file references and line numbers, markers, or sections.

### Naming

- Filenames: kebab-case matching the concept (e.g., attention-mechanism.md)
- Cross-references: use [[wikilinks]] for all internal links
- Source references: always link back to `docs/raw/` paths or code paths

## Workflows

### Capture (the everyday path)

During normal coding work, when something non-obvious is learned:
1. Create or enrich the relevant wiki page(s)
2. Update `docs/wiki/index.md`
3. Append one line to `docs/wiki/log.md`

Do this in passing — it should not interrupt the task at hand.

**Mandatory wiki updates after code changes:** After implementing new features, commands, or architectural changes in any submodule, update the corresponding wiki page(s) to document the change and append an entry to `docs/wiki/log.md`. This is not optional — wiki drift is a silent knowledge loss.

### Ingest (formal document intake)

1. Read the source document in `docs/raw/`
2. If working interactively, discuss key takeaways with the user
3. Create `docs/wiki/sources/[source-name].md` summary
4. Update or create concept/entity pages as needed
5. Update `docs/wiki/index.md` with new entries
6. Append to `docs/wiki/log.md`

### Query

1. Read `docs/wiki/index.md` to identify relevant pages
2. Read those pages and synthesize an answer
3. Cite sources using [[wikilinks]]
4. If the answer is novel and valuable, offer to save it as a new wiki page

### Lint

1. Scan all wiki pages for contradictions
2. Identify orphan pages (no incoming links)
3. Flag missing concepts referenced but not created
4. Find stale claims superseded by newer sources or code changes
5. Save results to `docs/outputs/lint-YYYY-MM-DD.md`
