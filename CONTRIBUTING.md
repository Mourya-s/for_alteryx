# Contributing to Alteryx to Databricks Migration Framework

First off, thank you for considering contributing! This project converts Alteryx workflows into deployable Databricks Asset Bundles, and it's designed to be extended — especially around adding support for new Alteryx tools. Contributions of all sizes are welcome, from fixing a typo in the docs to adding a whole new tool mapping in the parser.

## Code of Conduct

This project follows a Code of Conduct to ensure a welcoming and harassment-free experience for everyone.

## Getting Started

### 1. Repository Setup

Fork the repository, then clone your fork:

```bash
git clone https://github.com/<your-username>/for_alteryx.git
cd for_alteryx
```

Add the upstream remote so you can keep your fork in sync:

```bash
git remote add upstream https://github.com/Mourya-s/for_alteryx.git
```

### 2. Development Environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

To work on the migration pipeline itself, you'll want:

- Python 3.x
- Access to a Databricks workspace (for testing end-to-end deployment)
- A Gemini API key (free tier is fine for local iteration)
- A sample `.yxmd` (and `.yxmc` macros, if relevant) to test parser changes against — `workflows/Sample_Workflow1.yxmd` is included for this purpose

## Branch Naming Conventions

Create a new branch off `main` for each change, using one of the following prefixes:

| Prefix | Use for |
|---|---|
| `feature/` | New functionality (e.g. `feature/crosstab-tool-support`) |
| `fix/` | Bug fixes (e.g. `fix/macro-parsing-error`) |
| `docs/` | Documentation-only changes (e.g. `docs/update-readme-setup`) |
| `refactor/` | Non-behavioral code restructuring |
| `test/` | Adding or updating tests |
| `chore/` | Tooling, dependencies, CI config, etc. |

```bash
git checkout -b feature/crosstab-tool-support
```

## Commit Message Conventions

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<optional scope>): <short summary>

<optional body>
```

Common types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

Examples:

```
feat(parser): add support for CrossTab tool
fix(generator): correct join key mapping for Union tool
docs(readme): clarify macro upload requirements
```

Keep the summary line under ~72 characters, written in the imperative mood ("add", not "added").

## Pull Request Process

1. Make sure your branch is up to date with `upstream/main` before opening a PR:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```
2. Ensure your change:
   - Includes a clear description of **what** changed and **why**
   - References any related issue (e.g. `Closes #12`)
   - Includes tests or a sample workflow demonstrating the change, where applicable
   - Updates relevant documentation (README, inline comments, this file) if behavior changes
3. Open the PR against `main` and fill out the PR template.
4. Ensure CI (the `alteryx-migration.yml` workflow, plus any future test workflows) passes.
5. Respond to review feedback — a maintainer will merge once approved.


## Coding Standards

- Follow **PEP 8** for Python code.
- Prefer clear, descriptive names over abbreviations — this codebase is read by contributors extending the parser's tool mappings, so clarity matters more than brevity.
- Keep parser tool-extraction methods (`_extract_<tool>_config`) self-contained and consistent with the existing pattern shown in the README's [Extending the Parser](README.md#extending-the-parser) section.
- Avoid breaking changes to `workflow.json`'s schema without updating `generator.py` and documenting the change.

## Testing Expectations

- If you add support for a new Alteryx tool, include a minimal sample workflow (or a snippet of one) that exercises the new tool mapping.
- Verify the parser output (`workflow.json`) matches the expected structure for your new tool.
- Where possible, confirm the generated PySpark/Databricks code from `generator.py` runs correctly against sample data.
- Check `validate.log` output for your change and include it or a summary in the PR description if relevant.


## Documentation Guidelines

- Update `README.md` if you change setup steps, supported tools, secrets/configuration, or the pipeline flow.
- Keep diagrams in `docs/images/` and reference them with relative Markdown image links.
- Write in clear, concise language; prefer diagrams or tables over long paragraphs when describing structure or flow.
- Use fenced code blocks with language hints (` ```python `, ` ```yaml `, etc.) for all code samples.

## Issue Reporting Guidelines

When opening an issue, please include:

- A clear, descriptive title
- Steps to reproduce (for bugs), including the Alteryx tool(s) involved if parser-related
- Expected vs. actual behavior
- Relevant snippets from `workflow.json`, `llm_output.txt`, or `validate.log` (redact anything sensitive)
- Your environment (Python version, Databricks runtime, OS)

For feature requests, describe the Alteryx tool or capability you'd like supported, and — if possible — a sample workflow structure that uses it.

## Review Process

- All PRs require at least one maintainer review before merging.
- Reviewers will check for: correctness, consistency with the existing parser/generator patterns, documentation updates, and CI passing.
- Please be patient and responsive — most review feedback is aimed at keeping the parser extensible and the generated code reliable across a wide range of Alteryx workflows.

## Extending the Parser.py tools

-The parser is built to be extended rather than rewritten. Example: adding support for a new tool (`CrossTab`):

**Step 1 — Add the tool mapping** in `parser/parser.py`:

```python
PLUGIN_TOOL_MAP = {
    ...
    "CrossTab": "CrossTab",
}
```

**Step 2 — Add a configuration extractor:**

```python
def _extract_crosstab_config(self, node):
    config = {}
    cfg_root = self._get_config_root(node)
    if cfg_root is None:
        return config

    group_by = self._text(cfg_root.find(".//GroupByField"))
    header = self._text(cfg_root.find(".//HeaderField"))
    value = self._text(cfg_root.find(".//ValueField"))

    if group_by:
        config["group_by"] = group_by
    if header:
        config["header_field"] = header
    if value:
        config["value_field"] = value

    return config
```

**Step 3 — Register the extractor** in `_extract_configuration()`:

```python
handlers = {
    ...
    "CrossTab": self._extract_crosstab_config,
}
```

**Step 4 — Confirm the parsed output.** For an `Input → CrossTab → Output` workflow, the parser will emit something like:

```json
{
  "tool_id": "5",
  "tool_type": "CrossTab",
  "configuration": {
    "group_by": "Customer",
    "header_field": "Month",
    "value_field": "Sales"
  }
}
```

**Step 5 — Add generator support** in `generator.py`:

```python
if tool["tool_type"] == "CrossTab":
    generate_crosstab(tool)
```

Which produces the Spark equivalent:

```python
df.groupBy("Customer") \
  .pivot("Month") \
  .sum("Sales")
```

> **Rule of thumb:** the better the underlying LLM, the better the generated Spark/DAB code — this relationship is especially noticeable for complex workflows.



## Best Practices & Repository Etiquette

- Keep PRs focused — one feature/fix per PR rather than bundling unrelated changes.
- Don't commit contents of `generated/` from your own local runs unless the change is specifically about fixing generation logic — treat it as build output.
- Never commit real Databricks tokens, API keys, or workspace URLs; use the documented GitHub Secrets instead.
- Be respectful and constructive in issues, PRs, and reviews.
- When in doubt about a design decision (e.g., whether a tool should be treated as a reporting tool and skipped), open an issue to discuss before investing significant work.

## Contribution Workflow Summary

```
Fork → Clone → Branch → Code → Test → Commit (Conventional Commits) → Push → Open PR → Review → Merge
```

Thanks again for contributing — we look forward to your PR!
