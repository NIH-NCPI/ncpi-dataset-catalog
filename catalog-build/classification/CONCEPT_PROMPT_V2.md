# Concept Reorganization

You are organizing medical/clinical concept names within a mid-level category. You receive a list of concept names (with study counts) that all belong to the same mid-level subcategory.

Your job:

1. **Think first** — in the `reasoning` field, briefly identify synonym groups and plan the hierarchy.
2. **Merge synonyms** — concepts that refer to the exact same measurement but have different wording, spelling, or casing. Map the synonym to the better canonical name.
3. **Place concepts in a hierarchy** — assign each canonical concept a parent (or null for roots) to form a variable-depth is_a tree.

## Output format

Use a **flat list** of concept-parent pairs (not nested JSON):

```json
{
  "reasoning": "Your analysis here...",
  "synonyms": [{"synonym": "Old Name", "canonical": "Kept Name"}, ...],
  "concepts": [
    {"concept": "Broad Concept", "parent": null},
    {"concept": "Specific Concept", "parent": "Broad Concept"},
    ...
  ]
}
```

Each concept appears once in the `concepts` list with its parent reference. Root concepts have `"parent": null`.

## Synonym merging rules

- Only merge concepts that truly mean the **same measurement**. "Sitting Diastolic Blood Pressure" and "Seated Diastolic Blood Pressure" are synonyms. "Systolic Blood Pressure" and "Diastolic Blood Pressure" are NOT.
- Pick the most standard/recognizable name as canonical (prefer UMLS/SNOMED preferred terms).
- Use Title Case with **lowercase prepositions and articles** (a, an, and, at, by, for, in, of, on, or, the, to, with). Example: "Weight at Age 50", "History of Diabetes" — matching UMLS/SNOMED conventions.
- Prefer the name with the higher study count as canonical (it's more established).

## Hierarchy rules

- A child is a **more specific type** of its parent. "Standing Systolic Blood Pressure" is_a "Systolic Blood Pressure".
- The hierarchy can be any depth — go as deep as the domain requires.
- Root concepts (parent: null) are the broadest within this mid-level.
- You MAY create new parent nodes to group related concepts, even if the parent name was not in the input. For example, create "Cranial Measurements" to group "Head Circumference" and "Cranial Length".
- **No single-child parents**: Every parent should have at least 2 children. If a grouping concept would have only one child, keep both as siblings (both with parent: null or the same grandparent) instead.
- If concepts are peers (equally specific, not parent-child), give them the same parent.

## Examples

Input (mid-level: "Blood Pressure"):
```
- Systolic Blood Pressure (154 studies)
- Diastolic Blood Pressure (148 studies)
- Standing Systolic Blood Pressure (6 studies)
- Sitting Diastolic Blood Pressure (2 studies)
- Seated Diastolic Blood Pressure (2 studies)
- Mean Arterial Pressure (16 studies)
- Mean Arterial Blood Pressure (2 studies)
```

Output:
```json
{
  "reasoning": "Seated and Sitting Diastolic BP are synonyms (same posture, different wording). Mean Arterial Blood Pressure and Mean Arterial Pressure are synonyms. Standing SBP is a specific type of SBP. Sitting DBP is a specific type of DBP. MAP is a peer of SBP/DBP.",
  "synonyms": [
    {"synonym": "Seated Diastolic Blood Pressure", "canonical": "Sitting Diastolic Blood Pressure"},
    {"synonym": "Mean Arterial Blood Pressure", "canonical": "Mean Arterial Pressure"}
  ],
  "concepts": [
    {"concept": "Systolic Blood Pressure", "parent": null},
    {"concept": "Standing Systolic Blood Pressure", "parent": "Systolic Blood Pressure"},
    {"concept": "Diastolic Blood Pressure", "parent": null},
    {"concept": "Sitting Diastolic Blood Pressure", "parent": "Diastolic Blood Pressure"},
    {"concept": "Mean Arterial Pressure", "parent": null}
  ]
}
```

## Important

- Every **input** concept must appear exactly once: either in the `concepts` list or as a synonym source. Do not drop any input concepts.
- You may add new parent/grouping concepts that were not in the input — but every such invented node should have at least 2 children.
- Synonym canonical targets must exist in the `concepts` list.
- Use Title Case with lowercase prepositions/articles consistently. Preserve input concept names as-is unless they need preposition/article casing fixed (e.g. "Weight At Age 50" → "Weight at Age 50").
