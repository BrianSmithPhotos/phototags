# AI suggestion eval set

Sample images + human-written ground truth for comparing AI provider/model
suggestions against, via a standalone harness (not part of the app).

## Layout

- `images/` — sample photos, EXIF/IPTC/XMP stripped (GPS and any existing
  Description/Keywords removed) before being added here. Stripping matters for
  two reasons: privacy (no GPS leaks if this directory is committed), and
  avoiding contamination (an existing Description/Keywords field could leak the
  expected answer into the prompt context the harness sends to a model).
- `ground_truth.json` — your real ground truth, keyed by filename as it
  appears in `images/`. Not committed until it exists; see
  `ground_truth.example.json` for the format.
- `ground_truth.example.json` — template/format reference only, not real data.

## Ground truth format

```json
{
  "<filename in images/>": {
    "description": "<one-sentence human description>",
    "keywords": ["<lowercase keyword>", "..."]
  }
}
```

Match the style the app itself asks models for (see `SYSTEM_PROMPT` /
`_build_primary_prompt` in `ai_suggestion_service.py`): one concise sentence,
10-15 lowercase keywords, common + scientific names where applicable.
