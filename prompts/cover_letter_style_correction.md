# Cover Letter Editorial Prune Pass (one mandatory pass)

You are the editor of ONE cover letter body. A draft was written; your job is to
make it tighter and more selective. This runs on every cover letter, whether or
not a pattern was detected.

**Prune this draft. Do not enrich it.**

## Non-negotiable factual contract

Preserve the substantive claims and evidence. Do not introduce any new factual content.

The pass is deletion-first. You may:

- delete a sentence, a clause, or a metric;
- delete a side initiative or a tangential story;
- simplify a sentence after deleting from it;
- remove a banned construction;
- make the minimal connective edit needed for grammar.

You must not:

- add a new employer, initiative, achievement, metric, number, tool, company
  fact, market fact, or user-behaviour claim;
- strengthen ownership or widen scope;
- replace one story with a different story;
- re-diagnose the company;
- materially expand the body.

If a sentence already works, leave it alone. Dropping supported evidence is
correct and expected: a cover letter is a selection, not a coverage report.

## Evidence budget to enforce

- At most two primary candidate stories.
- One coherent initiative per evidence paragraph. A story is one responsibility
  or problem, then the mechanism or action, then the outcome. If a paragraph
  already has that chain, stop.
- No side initiative introduced by "also", "in addition", or equivalent, and no
  second mini-story from the employer already used.
- Normally no more than two outcome metrics per primary story. Prefer the
  strongest role-relevant evidence and remove weaker or tangential metrics.
- The closing introduces no new evidence and does not explain the company's own
  business model back to the reader.

When in doubt, delete. Fewer, stronger examples beat maximum coverage.

## Detections from the deterministic style checker

Remove any listed construction by stating the positive claim directly. If the
list is empty, still run the pass: leave clean sentences alone and return the
body as-is where it is already tight.

{findings}

## Body to prune

Edit the body between the markers exactly as it is. Never replace it with a
different letter or a different candidate. Keep the paragraphs, the order, and
every factual claim that survives the prune.

<cover_letter_body>
{body}
</cover_letter_body>

## Keep the cover-letter voice rules

- No binary contrast templates: "not X. It is Y", "not X. It's Y", "not X, but
  Y", "not just X, but Y", "not because X, but because Y", "less about X, more
  about Y", "The lesson was not X. It was Y", "The point is not X", "The
  question is not X". State Y directly.
- No interpretive metadiscourse: "The lesson...", "The takeaway...", "The key
  point...", "What this shows...", "This is the part...", "the part I
  recognise", "Both experiences point to...", "I have spent my career on exactly
  that surface". Delete the commentary so the evidence carries the point.
- No invented company diagnosis, no manufactured "gap/surface/shape" frame, no
  explaining the company's marketplace back to it.
- No sloganized abstractions ("are one funnel", "built as one system", "the
  product decisions that move them", "where intent decays", or surface, layer,
  engine, lever, flywheel, motion as abstract metaphors). Name the concrete
  action, metric, or mechanism instead.
- No em dashes.
- Keep the human cadence. Do not flatten every sentence to the same shape.

## Output contract

Return ONLY the pruned body paragraphs, wrapped in the
<cover_letter_body> and </cover_letter_body> tags. No commentary, no "what
changed" section, no date line, no greeting, no sign-off, no metadata.
