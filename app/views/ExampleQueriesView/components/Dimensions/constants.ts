import {
  PromptSuggestion,
  SUGGESTION_VARIANT,
} from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";

export type ExampleQuery = PromptSuggestion;

export interface FacetValueGroup {
  examples?: ExampleQuery[];
  label: string;
  values: string[];
}

export interface Dimension {
  description: string;
  examples: ExampleQuery[];
  explanation?: string;
  facetValues?: FacetValueGroup[];
  title: string;
}

export const DIMENSIONS: Dimension[] = [
  {
    description:
      "Search by hosting platform, molecular data type, or study design methodology.",
    examples: [
      {
        label: "Whole genome sequencing studies on AnVIL",
        query: "Whole genome sequencing studies on AnVIL",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Transcriptomic data in clinical trials",
        query: "Transcriptomic data in clinical trials",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Family trio studies with whole exome sequencing",
        query: "Family trio studies with whole exome sequencing",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    facetValues: [
      {
        examples: [
          {
            label: "Longitudinal cohort studies on BioData Catalyst",
            query: "Longitudinal cohort studies on BioData Catalyst",
            variant: SUGGESTION_VARIANT.CHIP,
          },
          {
            label: "Studies on Kids First Data Resource Center",
            query: "Studies on Kids First Data Resource Center",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Platforms",
        values: ["AnVIL", "BDC", "CRDC", "dbGaP", "KFDRC"],
      },
      {
        examples: [
          {
            label: "Studies with methylation data",
            query: "Studies with methylation data",
            variant: SUGGESTION_VARIANT.CHIP,
          },
          {
            label: "Case-control studies with genotyping arrays",
            query: "Case-control studies with genotyping arrays",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Data types",
        values: [
          "AMPLICON",
          "ATAC-seq",
          "Bisulfite-Seq",
          "ChIP-Seq",
          "CNV (NGS)",
          "CNV Genotypes",
          "Hi-C",
          "Metabolomics",
          "Methylation (CpG)",
          "miRNA-Seq",
          "mRNA Expression (Array)",
          "Proteomics",
          "RNA Seq (NGS)",
          "RNA-Seq",
          "SNP Genotypes (Array)",
          "SNP Genotypes (imputed)",
          "SNP Genotypes (NGS)",
          "SNP/CNV (Array)",
          "SNP/CNV Genotypes (imputed)",
          "SNP/CNV Genotypes (NGS)",
          "SNV (.MAF)",
          "Targeted-Capture",
          "WGA",
          "WGS",
          "WXS",
        ],
      },
      {
        examples: [
          {
            label: "Cross-sectional studies with genotyping data",
            query: "Cross-sectional studies with genotyping data",
            variant: SUGGESTION_VARIANT.CHIP,
          },
          {
            label: "Mendelian disease studies",
            query: "Mendelian disease studies",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Study designs",
        values: [
          "Case-Control",
          "Case Set",
          "Clinical Genetic Testing",
          "Clinical Trial",
          "Collection",
          "Control Set",
          "Cross-Sectional",
          "Family/Twin/Trios",
          "Interventional",
          "Mendelian",
          "Metagenomics",
          "Prospective Longitudinal Cohort",
          "Tumor vs. Matched-Normal",
          "Xenograft",
        ],
      },
    ],
    title: "Study metadata",
  },
  {
    description:
      "Search across 170,000+ phenotype variables classified into a hierarchical measurement vocabulary. Describe what a variable measures in plain language and the system matches it to the closest concept.",
    examples: [
      {
        label: "Studies measuring systolic blood pressure",
        query: "Studies measuring systolic blood pressure",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Studies with smoking data",
        query: "Studies with smoking data",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Studies with body mass index and cholesterol measurements",
        query: "Studies with body mass index and cholesterol measurements",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    explanation:
      'Measurements are organized in a 4-level hierarchy with ~20 top-level categories and ~6,300 leaf concepts. Searching a parent concept (e.g., "ECG measurements") returns all descendant variables across child concepts automatically.',
    title: "Harmonized variables",
  },
  {
    description:
      "Disease focus areas organized by the NLM Medical Subject Headings (MeSH) ontology. Describe a disease in plain language and the system matches it to the appropriate MeSH term.",
    examples: [
      {
        label: "Studies about type 2 diabetes",
        query: "Studies about type 2 diabetes",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Pancreatic cancer studies with transcriptomic data",
        query: "Pancreatic cancer studies with transcriptomic data",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Respiratory disease studies on BioData Catalyst",
        query: "Respiratory disease studies on BioData Catalyst",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    explanation:
      'MeSH terms are organized in a polyhierarchy of ~950 disease terms. Searching a broad term like "Cardiovascular Diseases" returns studies tagged with any descendant disease, such as Coronary Artery Disease, Atrial Fibrillation, or Heart Failure.',
    title: "MeSH disease hierarchy",
  },
  {
    description:
      "Search over GA4GH data use conditions using natural language. Describe your access requirements and the system maps them to consent code filters.",
    examples: [
      {
        label: "Studies where IRB approval is not required",
        query: "Studies where IRB approval is not required",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "General research use studies with whole genome sequencing",
        query: "General research use studies with whole genome sequencing",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Studies available for commercial use",
        query: "Studies available for commercial use",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    explanation:
      "Consent codes follow the GA4GH framework. Base codes include GRU (General Research Use), HMB (Health/Medical/Biomedical), and DS (Disease-Specific). Modifiers further restrict access: IRB (requires IRB approval), NPU (non-profit use only), PUB (publication required), COL (collaboration required), GSO (genetic studies only), and MDS (methods development only).",
    title: "Consent codes",
  },
  {
    description:
      "Genetically computed population ancestry across study participants.",
    examples: [
      {
        label: "Studies with East Asian ancestry participants",
        query: "Studies with East Asian ancestry participants",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label:
          "European and African American ancestry with whole genome sequencing",
        query:
          "European and African American ancestry with whole genome sequencing",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    facetValues: [
      {
        examples: [
          {
            label: "Studies with South Asian ancestry participants",
            query: "Studies with South Asian ancestry participants",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Computed ancestry values",
        values: [
          "African",
          "African American",
          "East Asian",
          "European",
          "Hispanic1",
          "Hispanic2",
          "Other",
          "Other Asian or Pacific Islander",
          "South Asian",
        ],
      },
    ],
    title: "Inferred ancestry",
  },
  {
    description: "Self-reported sex, race, and ethnicity of study cohorts.",
    examples: [
      {
        label: "Studies with Hispanic or Latino participants",
        query: "Studies with Hispanic or Latino participants",
        variant: SUGGESTION_VARIANT.CHIP,
      },
      {
        label: "Cohorts with Native Hawaiian or Pacific Islander participants",
        query: "Cohorts with Native Hawaiian or Pacific Islander participants",
        variant: SUGGESTION_VARIANT.CHIP,
      },
    ],
    facetValues: [
      {
        examples: [
          {
            label: "Studies with female participants",
            query: "Studies with female participants",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Sex",
        values: ["Female", "Male", "Other/Unknown"],
      },
      {
        examples: [
          {
            label: "Studies with Black or African American participants",
            query: "Studies with Black or African American participants",
            variant: SUGGESTION_VARIANT.CHIP,
          },
        ],
        label: "Race/Ethnicity",
        values: [
          "American Indian or Alaska Native",
          "Asian",
          "Black or African American",
          "Hispanic or Latino",
          "Multiple",
          "Native Hawaiian or Other Pacific Islander",
          "Other",
          "Unknown/Not Reported",
          "White",
        ],
      },
    ],
    title: "Demographics",
  },
];
