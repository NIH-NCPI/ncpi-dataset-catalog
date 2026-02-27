# Variable Classification Pipeline
# Usage: make <target>
#
# Prerequisites:
#   export ANTHROPIC_API_KEY='...'
#   or set in ../../.env

VENV = ../../backend/.venv/bin/python3

.PHONY: help seeds classify classify-study classify-v3 classify-v3-study evals evals-scaling summary summary-detail summary-studies namespace phenx-vocab phenx-inject isa hierarchy v4 subconcepts expand expand-dry-run expand-parents archetypes archetypes-dry-run archetypes-concept

help:
	@echo "Variable Classification Pipeline"
	@echo ""
	@echo "  classify       - Classify all studies with v4 multi-table batching (resumable)"
	@echo "  classify-study - Classify one study: make classify-study STUDY=phs000007"
	@echo "  evals          - Run classifier evals"
	@echo "  evals-scaling  - Test accuracy at scaled vocabulary sizes"
	@echo "  summary        - Summarize results grouped by NCPI category"
	@echo "  summary-detail - Summary with example variables per concept"
	@echo "  summary-studies - Top studies by match count"
	@echo ""
	@echo "  seeds          - Extract TOPMed seed concepts (R-code parsing)"
	@echo "  isa            - Generate ISA hierarchy via LLM"
	@echo "  hierarchy      - Dump ISA hierarchy as markdown"
	@echo "  namespace      - Transform v3 → v4 (add topmed: prefix + CUI)"
	@echo "  phenx-vocab    - Build PhenX concept vocabulary"
	@echo "  phenx-inject   - Inject PhenX ground-truth into v4 output"
	@echo "  v4             - Full v4 pipeline: namespace + phenx-vocab + isa + phenx-inject"
	@echo "  subconcepts    - Generate sub-concepts for broad concepts (e.g. FFQ)"
	@echo "  expand         - Expand vocabulary with 14 new phenotype categories + sub-concepts"
	@echo "  expand-parents - Add parent concepts only (no sub-concepts)"
	@echo "  archetypes     - Generate archetypes for large concepts (>200 vars)"
	@echo "  archetypes-dry-run - Show stats without calling LLM"
	@echo ""
	@echo "  classify-v3    - Classify all studies with v3 (single-table, legacy)"

# Extract seed concepts from TOPMed harmonized variable JSONs
seeds:
	$(VENV) extract_topmed_seeds.py

# Classify all studies with v4 multi-table batching
classify:
	$(VENV) classify_v4.py

# Classify a single study (v4)
classify-study:
	$(VENV) classify_v4.py --study $(STUDY)

# Legacy v3 classifier (single-table per LLM call)
classify-v3:
	$(VENV) classify_v3_topmed.py

classify-v3-study:
	$(VENV) classify_v3_topmed.py --study $(STUDY)

# Run classifier evals
evals:
	$(VENV) eval_v4.py

# Test accuracy at scaled vocabulary sizes (78, 200, 500 concepts)
evals-scaling:
	$(VENV) eval_vocab_scaling.py

# Summarize classification results grouped by NCPI category
summary:
	$(VENV) summarize_v3.py

# Summary with example variables per concept
summary-detail:
	$(VENV) summarize_v3.py --examples

# Top studies by match count
summary-studies:
	$(VENV) summarize_v3.py --by-study

# Transform v3 output → v4 (namespace prefixes + CUI)
namespace:
	$(VENV) namespace_v3_output.py

# Build PhenX concept vocabulary from protocol metadata
phenx-vocab:
	$(VENV) build_phenx_vocabulary.py

# Inject PhenX ground-truth mappings into v4 output
phenx-inject:
	$(VENV) inject_phenx_mappings.py

# Generate ISA hierarchy via LLM (requires ANTHROPIC_API_KEY)
isa:
	$(VENV) build_concept_isa.py

# Dump ISA hierarchy as markdown with variable counts
hierarchy:
	@$(VENV) show_hierarchy.py

# Generate sub-concepts for broad concepts (requires ANTHROPIC_API_KEY)
subconcepts:
	$(VENV) build_subconcepts.py

# Expand vocabulary: add 14 new parent concepts + sub-concepts (requires ANTHROPIC_API_KEY)
expand:
	$(VENV) expand_vocabulary.py

# Dry-run: show prompts without calling LLM
expand-dry-run:
	$(VENV) expand_vocabulary.py --dry-run

# Add parent concepts only, skip sub-concept generation
expand-parents:
	$(VENV) expand_vocabulary.py --parents-only

# Generate archetypes for large concepts (requires ANTHROPIC_API_KEY)
archetypes:
	$(VENV) build_archetypes.py

# Dry-run: show archetype stats without calling LLM
archetypes-dry-run:
	$(VENV) build_archetypes.py --dry-run

# Generate archetypes for a single concept: make archetypes-concept CONCEPT=topmed:ecg
archetypes-concept:
	$(VENV) build_archetypes.py --concept $(CONCEPT)

# Full v4 pipeline: namespace → phenx-vocab → isa → phenx-inject
v4: namespace phenx-vocab isa phenx-inject
