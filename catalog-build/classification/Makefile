# Variable Classification Pipeline
# Usage: make <target>
#
# Prerequisites:
#   export ANTHROPIC_API_KEY='...'
#   or set in ../../.env

VENV = ../../backend/.venv/bin/python

.PHONY: help seeds classify classify-study classify-v3 classify-v3-study evals evals-scaling summary summary-detail summary-studies namespace phenx-vocab phenx-inject isa hierarchy v4

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
	$(VENV) eval_v3_topmed.py

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

# Dump ISA hierarchy as markdown
hierarchy:
	@$(VENV) -c "\
	import json; \
	from collections import defaultdict; \
	isa = json.load(open('output/concept-isa.json')); \
	cats = json.load(open('output/ncpi-categories.json')); \
	children_of = defaultdict(list); \
	[children_of[r['parent']].append(r['child']) for r in isa]; \
	[v.sort() for v in children_of.values()]; \
	[\
	  (print(f'## {c[\"name\"]} (\`{c[\"concept_id\"]}\`)'), print(), \
	   [( \
	     (print(f'- **{ch}**'), [print(f'  - {gc}') for gc in children_of.get(ch, [])]) \
	     if children_of.get(ch) \
	     else print(f'- {ch}') \
	   ) for ch in children_of.get(c['concept_id'], ['*(empty)*'])], \
	   print()) \
	  for c in cats \
	]"

# Full v4 pipeline: namespace → phenx-vocab → isa → phenx-inject
v4: namespace phenx-vocab isa phenx-inject
