# Task 2 — No-code automation (n8n)

**Chosen flow: LLM auto-tags each person's skill category, written back to the DB.**

Why this one over the duplicate-alert flow: you already built real dedup logic in
Task 1 in code — building ANOTHER duplicate-checker in n8n would be redundant busywork.
The skill-tagging flow demonstrates something Task 1 didn't: an LLM node doing
classification and the automation writing back to the same database, which is closer
to "automate on top of the merged data" than a second dedup pass would be.

## What you need to build in the n8n UI (do this yourself — it's ~20-30 min in the
canvas, not something to fake from a JSON file alone. Understand each node.)

1. **Sign up** for n8n cloud free trial (or `npx n8n` to self-host locally — either
   is fine per the brief).

2. **Trigger node**: "Manual Trigger" (or Schedule Trigger, run every N minutes) —
   simplest way to demo it live without needing a public webhook URL.

3. **SQLite node** (or "Execute Command" running `sqlite3` if the SQLite node isn't
   available in your n8n version): query people who don't have a skill_category yet.
   ```sql
   SELECT person_id, display_name,
          COALESCE(
            (SELECT skills FROM naukri_application WHERE person_id = person.person_id LIMIT 1),
            (SELECT skills FROM gig_worker WHERE person_id = person.person_id LIMIT 1)
          ) AS skills
   FROM person
   WHERE skill_category IS NULL;
   ```
   (Run `ALTER TABLE person ADD COLUMN skill_category TEXT;` once, manually, before
   this — see `add_skill_category_column.sql` in this folder.)

4. **Loop over items** node (Split in Batches) so each person is processed one at a
   time by the LLM node.

5. **OpenAI / Anthropic node** (n8n has built-in nodes for both): prompt something
   like:
   ```
   Given this list of skills: {{$json.skills}}
   Classify this person into EXACTLY ONE category:
   automation-heavy, web dev, backend/data, or general.
   Reply with only the category name, nothing else.
   ```

6. **SQLite node (again)**: write the result back —
   ```sql
   UPDATE person SET skill_category = '{{$json.category}}' WHERE person_id = {{$json.person_id}};
   ```

7. **Run it**, screen-record the execution log showing each node firing and the
   final DB values changing (`SELECT person_id, display_name, skill_category FROM person;`).

8. **Export**: n8n menu → "Download" (or Ctrl+A select all nodes → Ctrl+C → paste into
   a `.json` file) → save as `skill_tagging_flow.json` in this folder before submitting.

## What to actually understand for the live defense
- Why a Loop node is needed (LLM nodes process one input at a time in the free tier
  patterns most people use; batching avoids overwhelming the API / rate limits).
- What happens on an LLM classification you disagree with (no validation currently —
  worth mentioning as a limitation in your stuck log or the stretch answer).
- Cost: one LLM call per person — fine for 60 people, would need batching/caching at
  5,000 (see `STRETCH.md`).
