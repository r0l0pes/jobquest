# German-Language Pipeline Support — June 3, 2026

**Status:** Spec complete, ready for implementation.
**Grilled by:** deepseek-v4-pro, June 3, 2026.

---

## What

Rodrigo is applying to German jobs where the JD is in German and the output (resume, cover letter, Q&A) should also be in German. Currently the pipeline always produces English output regardless of input language.

## Decisions (from grilling session)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Per-item language toggles** | Resume `EN/DE`, Cover `EN/DE`, Q&A `EN/DE`. No "Auto" — user sets explicitly per slot. |
| 2 | **Same template, translated content** | No structural changes to resume or cover letter layout. Photo, birth date, marital status: not added. |
| 3 | **No separate voice file** | Too much maintenance burden. Inject inline language instructions into `_load_voice_prefix()`. |
| 4 | **Tagline stays English** | "Experiments that accelerate revenue" unchanged. Rodrigo's brand identity. |
| 5 | **LaTeX: localized section titles + T1 encoding** | `Section*{Experience}` → `Section*{Berufserfahrung}`, etc. Add `\usepackage[T1]{fontenc}` for German hyphenation. |
| 6 | **Cover letter greeting: Du-detection** | If JD uses "Du" → `Liebes {company}-Team,`. Otherwise → `Sehr geehrtes {company}-Team,`. |
| 7 | **German anti-patterns from Wikipedia** | Avoid: "darüber hinaus", "zusammenfassend", "nicht nur... sondern auch", Partizipialschwänze, "es ist wichtig zu beachten". |
| 8 | **Date format: German convention** | `Berlin, 03.06.2026` (no country suffix, DD.MM.YYYY). |
| 9 | **Cover letter closing** | `Mit freundlichen Grüßen,` instead of `Kind regards,`. |
| 10 | **Cover letter title** | `Bewerbung als {role}, {company}` instead of `Application for {role}, at {company}`. |
| 11 | **Pipeline context saves language flags** | So reruns and tracker know what language was requested. |

---

## UI Changes

### web_ui.py

Per-slot additions. Inside `create_app_form(slot_num)`, after the cover letter checkbox row, add:

```
[Language]
  Resume:   [EN | DE]
  Cover:    [EN | DE]
  Q&A:      [EN | DE]
```

Defaults: all `EN`. Three `gr.Radio` components, each `choices=["EN", "DE"]`, `value="EN"`.

The language selections flow into `_run_pipeline()` as environment variables:
- `JOBQUEST_LANG_RESUME=EN|DE`
- `JOBQUEST_LANG_COVER=EN|DE`
- `JOBQUEST_LANG_QA=EN|DE`

### apply.py CLI

Add `--lang-resume DE`, `--lang-cover DE`, `--lang-qa DE` arguments. Each accepts `EN` or `DE`. Maps to the same env vars as the web UI.

---

## Pipeline Changes

### `modules/pipeline.py`

#### 1. Language context in pipeline state

`step_scrape_job` (or early initialization) reads the env vars and stores on `ctx`:

```python
ctx["lang"] = {
    "resume": os.getenv("JOBQUEST_LANG_RESUME", "EN"),
    "cover": os.getenv("JOBQUEST_LANG_COVER", "EN"),
    "qa": os.getenv("JOBQUEST_LANG_QA", "EN"),
}
```

Saved to `pipeline_context.json` for tracker/rerun awareness.

#### 2. `_load_voice_prefix()` — language injection

When any language flag is `DE`, append a compact German-language block after the voice prefix:

```
## Ausgabesprache

Output in German (Geschäftsdeutsch, authentischer Ton, keine akademische Sprache).
Passe den Ton der Stellenausschreibung und Unternehmenskommunikation an.

Vermeide diese KI-Muster:
- "darüber hinaus", "zusätzlich", "ferner", "zusammenfassend", "abschließend"
- "nicht nur... sondern auch", "es ist wichtig zu beachten", "es ist bemerkenswert"
- Partizipialkonstruktionen: "gewährleistend", "hervorhebend", "widerspiegelnd", "betonend"
- "steht als Zeugnis", "fasziniert weiterhin", "hinterlässt bleibenden Eindruck", "Wendepunkt"
- "Ich hoffe, das hilft", "Natürlich!", "lassen Sie mich wissen"
- Keine "Fazit"- oder "Zusammenfassung"-Abschnitte am Ende
- Keine Bewerbungs-Floskeln: "hiermit bewerbe ich mich", "mit großem Interesse"
```

This block is added only when at least one language flag is DE. The English voice rules (`rodrigo-voice-lite.md`) are still loaded — many rules (no em dashes, active voice, no hedging) apply in both languages. The German block overrides/adds German-specific rules.

#### 3. `step_tailor_resume` — section titles localization

When `ctx["lang"]["resume"] == "DE"`:

- The `jd_analysis` prompt (step 3a) stays in English (internal analysis). No change needed.
- The resume LaTeX generation (step 3b) output is in German because: (a) the JD is German, (b) the `_load_voice_prefix()` injects "Output in German", (c) the tailoring brief guides German output.
- After LaTeX generation, apply a post-processing pass that replaces English section titles:

```python
SECTION_MAP = {
    "Summary": "Zusammenfassung",
    "Experience": "Berufserfahrung",
    "Skills & Tools": "Fähigkeiten & Tools",
    "Languages": "Sprachen",
    "Education": "Ausbildung",
    "Certifications": "Zertifizierungen",
    "Rapid Prototyping & Automation": "Rapid Prototyping & Automatisierung",
    "Platforms & APIs": "Plattformen & APIs",
    "AI & ML": "KI & ML",
    "Product": "Produkt",
    "Analytics": "Analytik",
    "Tools": "Tools",
}
```

This is a regex-based post-pass: `\section*{English}` → `\section*{German}`. Applied in `step_write_tex` or as a post-processing step in `step_tailor_resume`.

- Add `\usepackage[T1]{fontenc}` if not already present (check before adding).
- English date months (July, August, etc.) are handled by the LLM — the prompt instructs German output, so the LLM will write "Jul", "Aug" as-is (month abbreviations are the same in German for these months), but "May" → "Mai", "March" → "März", etc. Post-processing regex catches months if LLM misses them.

#### 4. `step_compile_cover_letter` — German template

When `ctx["lang"]["cover"] == "DE"`:

- The Q&A cover letter body is already in German (from step 8).
- Template substitutions differ from English:

| Placeholder | English | German |
|---|---|---|
| `{role_title}` | `Application for {role}, at {company}` | `Bewerbung als {role}, {company}` |
| `{company_title}` | (not used) | `Liebes {company}-Team,` or `Sehr geehrtes {company}-Team,` |
| Closing | `Kind regards,` | `Mit freundlichen Grüßen,` |
| Date | `{place}, {date}` | `Berlin, DD.MM.YYYY` |

**Du-detection logic** for the greeting:
```python
def _use_du(job_description: str) -> bool:
    """Check if the JD uses informal 'Du' address."""
    return bool(re.search(r'\b[Dd]ich\b|\b[Dd]ein\b|\b[Dd]ir\b', job_description))
```

**Implementation approach**: Instead of creating a separate `cover_letter_de.tex`, the pipeline reads the English template and applies string replacements for the German substitutions. This avoids maintaining two templates. The replacements are done in `step_compile_cover_letter` when `ctx["lang"]["cover"] == "DE"`.

#### 5. `step_generate_qa` — German Q&A

When `ctx["lang"]["qa"] == "DE"`:

- The cover letter Q&A prepend uses the German cover letter question: "Schreibe einen Anschreiben-Text für diese Bewerbung..."
- The role framing text stays the same (internal context for the LLM about which experiences to foreground).
- The `_load_voice_prefix()` injection already handles "Output in German".
- The "Used: [Role] | [Metric]" tracking line can stay in English (internal artifact).

---

## LaTeX Encoding

For German resumes, add `\usepackage[T1]{fontenc}` in the preamble. This enables proper hyphenation of words containing umlauts (ä, ö, ü) and ß. It's added during the post-processing pass:

```python
if "\\usepackage[T1]{fontenc}" not in latex:
    latex = latex.replace(
        "\\usepackage[utf8]{inputenc}",
        "\\usepackage[utf8]{inputenc}\n\\usepackage[T1]{fontenc}",
    )
```

---

## Implementation Plan

### Step 1: UI — `web_ui.py`

- Add 3 `gr.Radio("EN", "DE")` components to `create_app_form()`
- Wire them through `_run_pipeline()` as env vars `JOBQUEST_LANG_RESUME`, `JOBQUEST_LANG_COVER`, `JOBQUEST_LANG_QA`

### Step 2: CLI — `apply.py`

- Add `--lang-resume`, `--lang-cover`, `--lang-qa` arguments

### Step 3: Pipeline state — `modules/pipeline.py`

- Early in pipeline (step 1 or before step 3), read env vars into `ctx["lang"]`
- Save to `pipeline_context.json`

### Step 4: Voice injection — `modules/pipeline.py`

- Modify `_load_voice_prefix()` to accept an optional `lang_flags` param
- When any flag is `DE`, append the German anti-pattern/tone block

### Step 5: Resume localization — `modules/pipeline.py`

- Post-processing pass after LaTeX generation in `step_tailor_resume`:
  - Replace English section titles with German
  - Add `\usepackage[T1]{fontenc}`
- Apply only when `ctx["lang"]["resume"] == "DE"`

### Step 6: Cover letter localization — `modules/pipeline.py`

- In `step_compile_cover_letter`, when `ctx["lang"]["cover"] == "DE"`:
  - Template string replacements for title, greeting, closing, date
  - Du-detection for greeting formal/informal choice
- `_latex_escape()` already handles umlauts (they're valid UTF-8)

### Step 7: Tests — `tests/`

- Unit test: `_use_du()` detection
- Unit test: section title replacement regex
- Unit test: T1 encoding insertion
- Unit test: cover letter German template substitutions
- Integration test: pipeline context saves language flags
- Smoke test: full pipeline with `--lang-resume DE --lang-cover DE --lang-qa DE` (dry-run)

---

## Files to Reference

- `web_ui.py` — UI form, `_run_pipeline()`, env var pass-through
- `apply.py` — CLI argument parsing
- `modules/pipeline.py` — `_load_voice_prefix()`, `step_tailor_resume`, `step_compile_cover_letter`, `step_generate_qa`, `step_write_tex`
- `templates/cover_letter.tex` — template substitutions for German
- `templates/resume.tex` — section title substitutions
- `prompts/rodrigo-voice-lite.md` — English voice rules (stay as-is, German block appended)

---

## Not in Scope

- **Photo or birth date in German resume** — Rodrigo explicitly excluded
- **Auto-detection of JD language** — user sets per-item toggles explicitly
- **Separate `rodrigo-voice-de.md`** — too much maintenance; inline injection instead
- **Bilingual mixed Q&A** — each question answered in target language; mixed JD handled by user setting each toggle
- **German ATS check** — stays in English (internal report for Rodrigo to read)
- **Resume variant-specific German taglines** — tagline stays English regardless of language
