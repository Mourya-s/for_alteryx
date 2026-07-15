# Alteryx to Databricks Migration Framework

Automatically convert Alteryx workflows (`.yxmd` / `.yxmc`) into deployable Databricks Asset Bundles (DAB) using an LLM-driven code generation pipeline, wired end-to-end through GitHub Actions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Build Status](https://github.com/Mourya-s/for_alteryx/actions/workflows/alteryx-migration.yml/badge.svg)](https://github.com/Mourya-s/for_alteryx/actions)
[![Python](https://img.shields.io/badge/python-3.x-EADME.md)

> TODO: Add release/version badge once versioning is established.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Example Workflow](#example-workflow)
- [Supported Inputs](#supported-inputs)
- [Generated Outputs](#generated-outputs)
- [Extending the Parser](#extending-the-parser)
- [Technologies Used](#technologies-used)
- [Error Handling & Logging](#error-handling--logging)
- [Roadmap](#roadmap)
- [FAQ](#faq)
- [License](#license)
- [Contact](#contact)

---

## Overview

This project migrates legacy **Alteryx** ETL workflows to **Databricks**. You commit an Alteryx workflow file to the repository, and a GitHub Actions pipeline takes over: it parses the workflow's XML into a structured JSON representation, sends that JSON to an LLM (Gemini) to generate equivalent PySpark code and Databricks Asset Bundle configuration, validates the result, and deploys it directly to your Databricks workspace.

The goal is to remove the manual, tool-by-tool rewrite work typically required when retiring an Alteryx workflow, while keeping a human-reviewable JSON representation and validation log at every step.

## Features

- **Automated parsing** of Alteryx `.yxmd` workflow XML into a normalized JSON intermediate representation
- **LLM-assisted code generation** — converts the parsed workflow into PySpark code and a Databricks Asset Bundle
- **One-push CI/CD** — pushing a workflow file triggers parsing, generation, validation, and deployment automatically
- **Validation gate** — generated bundles are checked against the expected structure before deployment
- **Extensible tool mapping** — new Alteryx tools can be added to the parser without rewriting the core engine
- **Macro-aware** — supports `.yxmc` macro files alongside the parent workflow (see [Supported Inputs](#supported-inputs) for current limits)
- **Reporting-tool aware skipping** — intentionally ignores presentation/reporting tools that fall outside the ETL migration scope

## Architecture Overview

<img width="844" height="332" alt="architecture-overview" src="https://github.com/user-attachments/assets/dd11d36d-5ab6-4da7-93f0-f9eb8e4ce0f3" />

At a high level:

1. A user exports an **Alteryx workflow** (`.yxmd`) — and any macros (`.yxmc`) it depends on — from Alteryx Designer.
2. The workflow (and macro files) are added to the repository's `workflows/` directory.
3. Databricks and LLM credentials are configured as **GitHub Secrets**.
4. A `git push` triggers the `alteryx-migration.yml` GitHub Actions workflow.
5. The pipeline parses, generates, validates, and deploys — landing the final Databricks Asset Bundle in your workspace.

### CI/CD pipeline detail

<img width="289" height="434" alt="cicd-workflow-diagram" src="https://github.com/user-attachments/assets/3c910693-9191-408e-932f-7470c51e09fc" />

**CI process:**
1. Trigger on push and read the uploaded `.yxmd` file(s)
2. `parser.py` converts the XML into `workflow.json` (a compact JSON format chosen to minimize LLM token usage)
3. `workflow.json` is sent to the LLM, which returns Databricks Asset Bundle (DAB) code and PySpark (`workflow.py`)
4. `validate.log` records validation of both the generated Spark code and the DAB before anything is pushed further

**CD process:**
1. Databricks CLI is configured using the `DATABRICKS_HOST` / `DATABRICKS_TOKEN` secrets
2. The generated DAB is validated against the expected `jobs.yml` structure and cross-checked against the generated Spark code
3. The workspace path is resolved and the DAB + Spark code are deployed
4. A final check confirms both artifacts exist at the expected Databricks workspace path

> A live, editable version of the full workflow diagram is available on Excalidraw: https://excalidraw.com/helleo#json=G5IFdsWDGkR5Ombka2nW8,ZqlzCqkoqu86Si1oh3f0-A

## Repository Structure

<img width="260" height="498" alt="repository-tree" src="https://github.com/user-attachments/assets/255322a6-a81c-43d6-beed-12deaf3ba909" />

```
for_alteryx/
├── .github/
│   └── workflows/
│       └── alteryx-migration.yml   # GitHub Actions pipeline definition
├── workflows/
│   ├── Sample_Workflow1.yxmd       # Sample / user-supplied Alteryx workflow
│   ├── Macro1.yxmc                 # (optional) Alteryx macro files
│   └── Macro2.yxmc
├── parser/
│   └── parser.py                   # Reads Alteryx XML, extracts tools/dependencies/logic
├── generator.py                    # Converts workflow.json into Databricks artifacts
├── generated/                      # Auto-generated — do not edit by hand
│   ├── workflow.json                # Intermediate JSON representation
│   ├── llm_output.txt                # Raw LLM response
│   ├── validate.log                  # Validation results for the generated DAB
│   ├── databricks.yml                # Main Databricks Asset Bundle config
│   ├── .databricks/                  # Databricks bundle metadata (deployment state, IDs)
│   ├── resources/
│   │   └── jobs.yml                  # Databricks Jobs definition
│   ├── src/
│   │   └── workflow.py               # Generated PySpark code
│   └── workflows/
│       └── migration.yml             # Migration workflow steps (parse → transform → deploy)
├── requirements.txt                 # Python dependencies
└── README.md
```

> TODO: Confirm whether `generated/` is committed to the repo or produced/consumed purely within the CI run (i.e., should it be `.gitignore`d?).

## Prerequisites

- A **Databricks workspace** (Azure Databricks recommended)
- A **GitHub repository** you can push to and configure secrets on
- A **Gemini API key** ([Google AI Studio](https://aistudio.google.com/)) — the free tier is sufficient to start; larger or more complex workflows may need a higher tier
- Python 3.x (for local development/testing of the parser and generator)

## Installation

Clone the repository (or fork it first if you plan to contribute back):

```bash
git clone https://github.com/Mourya-s/for_alteryx.git
cd for_alteryx
pip install -r requirements.txt
```

## Configuration

Before pushing a workflow, configure the following **GitHub Actions secrets**:

Navigate to: **Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Description |
|---|---|
| `DATABRICKS_HOST` | URL of your Databricks workspace, e.g. `https://adb-xxxxxxxxxxxx.xx.azuredatabricks.net` (Azure Databricks recommended) |
| `DATABRICKS_TOKEN` | A Databricks Personal Access Token. Generate it via **Profile Icon → Settings → Developer → Access Tokens → Manage → Generate New Token**. Choose **"All APIs"** for the token scope for the best compatibility. |
| `GEMINI_API_KEY` | Your Gemini API key. The free tier works for getting started; use a higher tier for larger/more complex workflows. |

## Usage

**To test the project with the sample workflow:** simply push the repository as-is — `workflows/Sample_Workflow1.yxmd` is already included.

**To migrate your own workflow:**

1. Export your workflow from Alteryx Designer as `.yxmd`.
2. Place it (and any `.yxmc` macros it depends on) inside `workflows/`:
   ```
   workflows/
   ├── Sample_Workflow1.yxmd
   ├── Macro1.yxmc
   └── Macro2.yxmc
   ```
   > It's recommended to keep the same file name(s) used in Alteryx when uploading.
3. Commit and push:
   ```bash
   git add .
   git commit -m "Added Alteryx workflow"
   git push origin main
   ```
4. Monitor the pipeline under the repository's **Actions** tab.
5. Once complete, find the generated assets in your Databricks workspace at:
   ```
   Workspace → Users → <your-user-id> → alteryx_migration → dev → files
   ```

## How It Works

```
Alteryx Workflow (.yxmd / .yxmc)
        │
        ▼
  GitHub Actions
        │
        ▼
   Parser Engine  ──────►  workflow.json
        │
        ▼
 Databricks Generator (LLM)
        │
        ▼
 Databricks Asset Bundle
        │
        ▼
   Databricks Workspace
```

<img width="253" height="233" alt="pipeline-flow-simple" src="https://github.com/user-attachments/assets/3c738689-bfe5-4c1b-9d5d-bfc6b692dc61" />

## Example Workflow

A successful run walks through the following GitHub Actions job steps:

<img width="388" height="427" alt="github-actions-run-example" src="https://github.com/user-attachments/assets/79472de2-aa37-412d-97cc-467e27f8b5e2" />
`Set up job → Checkout → Setup Python → Install Dependencies → Install Databricks CLI → Check Databricks CLI → Parse Workflow → Generate DAB → Debug Generated Files → Configure Databricks → Debug Databricks Auth → Validate Bundle → Deploy Bundle → Debug Generated Files → Post Setup Python → Post Checkout → Complete job`

## Supported Inputs

- **`.yxmd`** — standard Alteryx workflow files
- **`.yxmc`** — Alteryx macro files, when uploaded **alongside** the parent workflow that references them

**Current limitations:**

- **Macros:** the parser currently cannot inspect the internal logic of a macro from within the parent workflow file alone — upload the macro's own `.yxmc` file in addition to the workflow.
- **Reporting / analytical tools** are intentionally skipped by design, since this project targets SDP/DAB (ETL) generation rather than reporting output. Skipped tool categories include: Render, Layout, Text Box, Reporting Table, Report Map, Document Builder, PowerPoint Output, Report Header/Footer, and most other Reporting-category tools.
- **Unknown/new tools:** the parser is designed to skip gracefully rather than crash on tools it doesn't recognize yet — see [Extending the Parser](#extending-the-parser) to add support.
- Generated code quality scales with the capability of the underlying LLM, particularly for complex workflows.

## Generated Outputs

Each pipeline run produces the following, under `generated/`:

| File | Description |
|---|---|
| `workflow.json` | Parsed, normalized intermediate representation of the Alteryx workflow |
| `llm_output.txt` | Raw output returned by the LLM |
| `validate.log` | Validation results for the generated Databricks Asset Bundle |
| `databricks.yml` | Databricks Asset Bundle root configuration |
| `resources/jobs.yml` | Databricks Job definitions |
| `src/workflow.py` | Generated PySpark implementation of the workflow |
| `workflows/migration.yml` | Migration steps (parse → transform → deploy) |
| `.databricks/` | Bundle deployment metadata/state |

## Extending the Parser

The parser is built to be extended rather than rewritten. Example: adding support for a new tool (`CrossTab`):

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

## Technologies Used

- **Alteryx** (`.yxmd` / `.yxmc`) — source workflow format
- **Python** — parser and generator implementation
- **Google Gemini API** — LLM-driven code generation
- **Databricks Asset Bundles (DAB)** — deployment packaging
- **PySpark** — generated transformation code
- **GitHub Actions** — CI/CD orchestration
- **Databricks CLI** — bundle validation and deployment

## Error Handling & Logging

- **`validate.log`** captures validation results for both the generated Spark code (SDP) and the Databricks Asset Bundle before deployment proceeds.
- **`llm_output.txt`** preserves the raw LLM response for each run, useful for debugging unexpected generation results.
- The parser is designed to **skip unknown/unsupported tools** rather than fail the whole run — see [Supported Inputs](#supported-inputs).
- CI job steps include explicit **debug steps** ("Debug Generated Files", "Debug Databricks Auth") to surface configuration or authentication issues before deployment is attempted.

> TODO: Document specific exit codes / failure conditions once formalized.

## Roadmap

- [ ] Extend `parser.py` to support all Alteryx tools, including reporting-category tools
- [ ] Add a testing framework to compare native Alteryx workflow output against the generated SDP/Databricks output
- [ ] Broaden parsing coverage across the full range of `.yxmd` and `.yxmc` files

## FAQ

**Q: Can I migrate a workflow that uses Alteryx macros?**
A: Yes — upload both the parent `.yxmd` workflow and every `.yxmc` macro file it depends on into `workflows/`. The parser currently cannot see inside a macro's logic from the parent workflow alone.

**Q: Why isn't my Reporting tool showing up in the generated output?**
A: Reporting/analytical tools (Render, Layout, Text Box, Reporting Table, Report Map, Document Builder, PowerPoint Output, Report Header/Footer, etc.) are intentionally skipped — this project targets ETL (SDP/DAB) generation, not report generation.

**Q: The parser hit a tool it doesn't recognize — will the pipeline fail?**
A: No, it's designed to skip unrecognized tools rather than break. If you need that tool supported, see [Extending the Parser](#extending-the-parser).

**Q: Which Gemini tier do I need?**
A: The free tier is enough to get started. Larger or more complex Alteryx workflows may need a higher usage tier for reliable generation.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

## Contact

- **Maintainer:: Mourya S
- **Email:: mourya04reddy@gmail.com
- **Issues:[GitHub Issues](https://github.com/Mourya-s/for_alteryx_migration)
