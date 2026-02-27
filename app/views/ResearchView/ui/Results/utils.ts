import { TableOptions } from "@tanstack/react-table";
import { AssistantMessage } from "@databiosphere/findable-ui/lib/views/ResearchView/state/types";
import { Response } from "../../types/response";
import { Study } from "../Datasets/types/study";
import { COLUMNS as STUDY_COLUMNS } from "./study/columns";
import { COLUMNS as VARIABLE_COLUMNS } from "./variable/columns";
import { Variable } from "../Datasets/types/variable";

type StudyOptions = Omit<TableOptions<Study>, "getCoreRowModel">;
type VariableOptions = Omit<TableOptions<Variable>, "getCoreRowModel">;

/**
 * Utility function to determine table options based on the response message.
 * If there are studies in the response, it returns options for the study table.
 * Otherwise, it returns options for the variable table.
 * @param message - The assistant message containing the response data.
 * @returns Table options for either studies or variables.
 */
export function getOptions(
  message: AssistantMessage<Response>
): StudyOptions | VariableOptions {
  if (message.response.totalStudies > 0) {
    return {
      columns: STUDY_COLUMNS,
      data: STUDIES,
      // data: message.response.studies,
      getRowId: (row: Study) => row.title,
    };
  }
  return {
    columns: VARIABLE_COLUMNS,
    data: message.response.variables,
    getRowId: (row: Variable) => row.variableName,
  };
}

const STUDIES = [
  {
    consentCodes: ["GRU"],
    dataTypes: ["RNA-Seq", "WGS"],
    dbGapId: "phs000550",
    demographics: {
      computedAncestry: null,
      raceEthnicity: {
        categories: [
          {
            count: 3,
            label: "White",
            percent: 75,
          },
          {
            count: 1,
            label: "Unknown/Not Reported",
            percent: 25,
          },
        ],
        n: 4,
      },
      sex: {
        categories: [
          {
            count: 2,
            label: "Male",
            percent: 50,
          },
          {
            count: 1,
            label: "Female",
            percent: 25,
          },
          {
            count: 1,
            label: "Other/Unknown",
            percent: 25,
          },
        ],
        n: 4,
      },
    },
    focus: "Pancreatic Neoplasms",
    participantCount: 4,
    platforms: ["dbGaP"],
    studyDesigns: ["Case Set"],
    title: "Characterization of Pancreatic Adenocarcinoma Patients Using NGS",
  },
  {
    consentCodes: ["HMB-IRB-NPU"],
    dataTypes: ["RNA-Seq", "SNP Genotypes (NGS)", "RNA Seq (NGS)"],
    dbGapId: "phs003002",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 35,
    platforms: ["dbGaP"],
    studyDesigns: ["Clinical Trial"],
    title:
      "A Platform Study of Combination Immunotherapy for the Neoadjuvant and    Adjuvant Treatment of Patients with Surgically Resectable    Adenocarcinoma of the Pancreas",
  },
  {
    consentCodes: ["HMB-IRB-NPU"],
    dataTypes: ["RNA-Seq"],
    dbGapId: "phs003563",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 3,
    platforms: ["dbGaP"],
    studyDesigns: ["Collection"],
    title:
      "Transfer Learning Associates CAFs with EMT and Inflammation in Tumor    Cells in Human Tumors and Organoid Co-Culture in Pancreatic Ductal    Adenocarcinoma",
  },
  {
    consentCodes: ["DS-PACA"],
    dataTypes: ["RNA-Seq", "SNP/CNV Genotypes (NGS)", "Targeted-Capture"],
    dbGapId: "phs003597",
    demographics: {
      computedAncestry: null,
      raceEthnicity: {
        categories: [
          {
            count: 259,
            label: "White",
            percent: 93.2,
          },
          {
            count: 11,
            label: "Other",
            percent: 4,
          },
          {
            count: 8,
            label: "Asian",
            percent: 2.9,
          },
        ],
        n: 278,
      },
      sex: null,
    },
    focus: "Pancreatic Neoplasms",
    participantCount: 278,
    platforms: ["dbGaP"],
    studyDesigns: ["Tumor vs. Matched-Normal"],
    title:
      "Ongoing Replication Stress Tolerance and Clonal T Cell Responses    Distinguish Liver and Lung Recurrence and Patient Outcomes in    Pancreatic Ductal Adenocarcinoma",
  },
  {
    consentCodes: ["HMB-IRB-NPU"],
    dataTypes: ["RNA-Seq", "WGS", "WXS"],
    dbGapId: "phs003600",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 75,
    platforms: ["dbGaP"],
    studyDesigns: ["Clinical Trial"],
    title:
      "Comprehensive Genomic Data Deposition for Pancreatic Cancer Precision    Medicine Studies: Clinical Trials NCT02451982 and NCT02648282",
  },
  {
    consentCodes: ["DS-PAD"],
    dataTypes: ["RNA-Seq"],
    dbGapId: "phs003641",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 1,
    platforms: ["dbGaP"],
    studyDesigns: ["Xenograft"],
    title:
      "Collagen XVII Promotes Pancreatic Cancer Through Regulation of PIK3R5",
  },
  {
    consentCodes: ["GRU", "DS-PAD"],
    dataTypes: ["RNA-Seq", "ssRNA-seq"],
    dbGapId: "phs003751",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 19,
    platforms: ["dbGaP"],
    studyDesigns: ["Collection"],
    title:
      "Dynamic Evolution of Fibroblasts Revealed by Single Cell RNA Sequencing    of Human Pancreatic Cancer",
  },
  {
    consentCodes: ["HMB-IRB-NPU"],
    dataTypes: ["RNA-Seq"],
    dbGapId: "phs003798",
    demographics: {
      computedAncestry: null,
      raceEthnicity: {
        categories: [
          {
            count: 55,
            label: "White",
            percent: 90.2,
          },
          {
            count: 5,
            label: "Black or African American",
            percent: 8.2,
          },
          {
            count: 1,
            label: "Asian",
            percent: 1.6,
          },
        ],
        n: 61,
      },
      sex: null,
    },
    focus: "Pancreatic Neoplasms",
    participantCount: 61,
    platforms: ["dbGaP"],
    studyDesigns: ["Clinical Trial"],
    title:
      "A Phase II Study: CRS207/GVAX Plus Anti-PD1 and Anti-CTLA4 Recruits    Mesothelin- and KRAS-Specific T cells into PDAC",
  },
  {
    consentCodes: ["HMB-IRB-NPU"],
    dataTypes: ["RNA-Seq"],
    dbGapId: "phs003862",
    demographics: null,
    focus: "Pancreatic Neoplasms",
    participantCount: 16,
    platforms: ["dbGaP"],
    studyDesigns: ["Case Set"],
    title:
      "Spatial Transcriptomics of Vaccine Therapy With or Without    Cyclophosphamide in Treating Patients Undergoing Chemotherapy and    Radiation Therapy for Stage I or Stage II Pancreatic Cancer That Can    Be Removed by Surgery",
  },
];
