# Pipeline Fixes — To Do

## Notion API notes (notion-client v2.7.0)

The installed SDK version changed the query API:
- **Old (broken):** `notion.databases.query(database_id=...)`
- **New (correct):** `notion.data_sources.query(data_source_id=<collection_id>)`

The collection ID differs from the database ID. Get it at runtime:
```python
db = notion.databases.retrieve(database_id=DB_ID)
collection_id = db["data_sources"][0]["id"]
```

Affected code: `scripts/notion_reader.py` `read_database()` at line 139 — currently unused by pipeline, but must be fixed before wiring up DB reads.

**DB details (standalone databases created 2026-02-19):**
- Skills & Keywords: DB ID `6a135aee-b665-4e48-84a3-032ce8e473b2` | Collection ID `716c48f6-414a-4327-8b0b-bf5c2b8d1861` | title property: `Name`
- Q&A Templates: DB ID `d068267a-007a-4981-b470-49f77d7a864c` | Collection ID `6de20f75-b3b2-4e39-87a2-d8b67ec16d17` | title property: `Name`

---

## 1. Skills & Keywords DB not being read by pipeline

`NOTION_SKILLS_KEYWORDS_DB_ID` is now populated (66 skills across 6 categories) but nothing in the codebase reads from it.

**Intended use:** Feed step 5 (ATS keyword coverage check) with the canonical list of Rodrigo's skills so the ATS check does structured coverage matching rather than pure LLM inference.

**What needs to happen:**
- Fix `read_database()` in `scripts/notion_reader.py` to use `data_sources.query()` (see API note above)
- Update `modules/pipeline.py` step 5 to call `notion_reader.py database <SKILLS_KEYWORDS_DB_ID>` and pass the skills list into the ATS prompt
- Update `prompts/ats_check.md` to accept the skills list as structured input

## 2. Q&A Templates DB not being read by pipeline

`NOTION_QA_TEMPLATES_DB_ID` is configured and schema is ready (empty — populate with real answers first).

**Intended use:** Step 8 (Generate Q&A answers) should pull pre-written templates from this DB so answers are grounded in Rodrigo's real voice rather than generated from scratch.

**What needs to happen:**
- Populate the Q&A Templates DB with real answers (Rodrigo does this in Notion UI)
- Fix `read_database()` in `scripts/notion_reader.py` (same API fix as above)
- Update `modules/pipeline.py` step 8 to read matching templates from the DB before generating Q&A
- Update `prompts/qa_generator.md` to accept existing templates as context
