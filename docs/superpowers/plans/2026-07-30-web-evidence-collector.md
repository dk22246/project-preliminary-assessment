# Web Evidence Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline execution selected by the user). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional, official-source web evidence collector that produces validated UTF-8 evidence ledgers before existing policy and report gates.

**Architecture:** Keep crawling concerns outside report rendering. A small standard-library collector validates source domains, fetches one public page at a time, extracts readable HTML and PDF/DOCX links, and writes an auditable `evidence.json`; a separate validator checks its schema, local content and failures. The existing report pipeline optionally validates this ledger without changing policy-card rules.

**Tech Stack:** Python 3 standard library (`urllib`, `html.parser`, `json`, `hashlib`, `unittest`); current HTML/Word/PDF pipeline.

---

### Task 1: Add the evidence-ledger contract and source registry

**Files:**
- Create: `references/source-registry.md`
- Create: `schemas/evidence.schema.json`
- Create: `scripts/evidence_collectors/__init__.py`
- Create: `scripts/evidence_collectors/registry.py`
- Test: `tests/test_web_evidence.py`

- [ ] **Step 1: Write failing domain and schema-contract tests**

```python
def test_rejects_unregistered_commercial_domain():
    self.assertFalse(is_allowed_url("https://example.com/article", set()))

def test_allows_hainan_tax_authority_url():
    self.assertTrue(is_allowed_url("https://hainan.chinatax.gov.cn/x", set()))
```

- [ ] **Step 2: Run the test and verify it fails because the module is absent**

Run: `python -X utf8 -m unittest tests.test_web_evidence -v`

Expected: import failure for `evidence_collectors.registry`.

- [ ] **Step 3: Implement the registry and static evidence JSON schema**

```python
OFFICIAL_HOSTS = {"hainan.chinatax.gov.cn", "haikou.customs.gov.cn", "haikou.pbc.gov.cn", "www.safe.gov.cn", "www.cninfo.com.cn", "www.sse.com.cn", "www.szse.cn", "www.hkexnews.hk", "www.sec.gov"}

def is_allowed_url(url: str, explicit_hosts: set[str]) -> bool:
    # Require HTTPS and accept an official .gov.cn host, a registered disclosure host,
    # or an explicitly supplied enterprise host.
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `python -X utf8 -m unittest tests.test_web_evidence -v`

Expected: domain tests pass.

### Task 2: Implement extraction, collection and evidence validation

**Files:**
- Create: `scripts/evidence_collectors/html_extract.py`
- Create: `scripts/collect_web_evidence.py`
- Create: `scripts/validate_evidence.py`
- Test: `tests/test_web_evidence.py`

- [ ] **Step 1: Write failing HTML extraction and invalid-ledger tests**

```python
def test_extracts_visible_text_and_document_links():
    result = extract_html("<title>政策</title><p>正文</p><a href='/a.pdf'>附件</a>", "https://hainan.chinatax.gov.cn/p")
    self.assertIn("正文", result.text)
    self.assertEqual(result.attachments[0]["file_type"], "pdf")

def test_validator_rejects_non_allowlisted_source():
    errors = validate_ledger({"evidence": [{"source_url": "https://example.com/x"}]}, Path("."))
    self.assertTrue(any("允许来源" in error for error in errors))
```

- [ ] **Step 2: Run the tests and verify they fail for missing behavior**

Run: `python -X utf8 -m unittest tests.test_web_evidence -v`

Expected: import or assertion failures for HTML extraction and `validate_ledger`.

- [ ] **Step 3: Implement the minimum collection path**

```python
def collect(url: str, purpose: str, out_dir: Path, explicit_hosts: set[str]) -> dict:
    # Reject disallowed hosts before I/O; fetch public HTML with urllib;
    # write UTF-8 Markdown; calculate SHA-256; record title, publisher,
    # canonical URL, fetched_at, HTTP/extraction status and errors.
```

The collector must use short timeouts and bounded retries, retain failed records, normalize duplicate URLs, and only discover same-page PDF/DOCX links. The validator must require all metadata for successful records, an error for failed records, a permitted source URL, unique canonical URL/content hash, and an existing content file.

- [ ] **Step 4: Run focused tests and command-line validation**

Run: `python -X utf8 -m unittest tests.test_web_evidence -v`

Expected: extraction, allowlist and validation tests pass.

### Task 3: Connect the collector to the Skill workflow and pipeline

**Files:**
- Modify: `SKILL.md`
- Modify: `references/evidence-intake.md`
- Modify: `scripts/run_report_pipeline.py`
- Modify: `scripts/preflight.py`
- Create: `examples/evidence-sample.json`
- Create: `examples/evidence-sample/official-policy.md`
- Test: `tests/test_deployment_preflight.py`
- Test: `tests/test_web_evidence.py`

- [ ] **Step 1: Write failing pipeline/preflight tests**

```python
def test_preflight_validates_evidence_sample(self):
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "preflight.py")], cwd=ROOT, text=True, capture_output=True)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertIn("网页证据台账有效", result.stdout)
```

- [ ] **Step 2: Run the test and verify it fails before integration**

Run: `python -X utf8 -m unittest tests.test_deployment_preflight.DeploymentPreflightTests.test_preflight_validates_evidence_sample -v`

Expected: assertion failure because the preflight result has no web-evidence validation.

- [ ] **Step 3: Add optional pipeline input and concise operating instructions**

```python
parser.add_argument("--evidence", help="optional validated web evidence ledger")
if args.evidence:
    run([sys.executable, str(SCRIPTS / "validate_evidence.py"), args.evidence])
```

Document that agents first find official candidate URLs, then run the collector and validator; only verified facts may enter `report-data.json`. Explicitly state that collector output is evidence, not policy eligibility, and existing policy scope validation remains mandatory.

- [ ] **Step 4: Run targeted integration tests**

Run: `python -X utf8 -m unittest tests.test_web_evidence tests.test_deployment_preflight -v`

Expected: all targeted tests pass.

### Task 4: Verify the complete portable Skill and publish

**Files:**
- Modify: `docs/superpowers/specs/2026-07-30-web-evidence-collector-design.md` only if implementation reveals a material design correction.
- Modify: `docs/superpowers/plans/2026-07-30-web-evidence-collector.md` to mark completed steps.

- [ ] **Step 1: Run the full test suite**

Run: `python -X utf8 -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run portable preflight and HTML smoke test**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\run_utf8.ps1 -Python <bundled-python> scripts/preflight.py --smoke`

Expected: UTF-8, evidence sample, policy gates and HTML smoke test pass.

- [ ] **Step 3: Inspect changed files and publish only Skill sources**

Run: `git status --short; git diff --check; git add SKILL.md references schemas scripts tests examples docs .editorconfig .gitattributes; git commit -m "feat: add auditable web evidence collector"; git push origin main`

Expected: no whitespace errors; no `outputs/` files staged; commit reaches the public repository.

## Self-review

- Spec coverage: Tasks 1–2 implement allowlisted collection, Markdown/PDF/DOCX discovery, metadata, retries, dedupe and validation; Task 3 integrates it without weakening policy gates; Task 4 covers regression, UTF-8 portability and publication.
- Placeholder scan: no deferred behavior is required for the initial collector; JavaScript rendering and Firecrawl adapters remain explicitly out of scope.
- Type consistency: `evidence.json` is the only collector output; `validate_evidence.py` is the same validation command used by both pipeline and preflight.
