import fetch from "node-fetch";
import { DbGapId } from "../app/apis/catalog/ncpi-catalog/common/entities";
import { Platform } from "./constants";
import {
  getPlatformStudiesStudyIds,
  sourcePath,
  updatePlatformStudiesAndReportNewStudies,
} from "./utils";

interface AnvilDatasetsResponse {
  termFacets: {
    "datasets.registered_identifier": {
      terms: Array<{
        term: string | null;
      }>;
    };
  };
}

const ANVIL_DATASETS_URL =
  "https://service.explore.anvilproject.org/index/datasets";

async function fetchAnvilIds(): Promise<DbGapId[]> {
  const response = await fetch(ANVIL_DATASETS_URL);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  const data = (await response.json()) as AnvilDatasetsResponse;
  const ids = new Set<DbGapId>();
  for (const { term } of data.termFacets["datasets.registered_identifier"]
    .terms) {
    const idMatch = term && /^phs\d+/.exec(term);
    if (idMatch) {
      ids.add(idMatch[0]);
    }
  }
  return Array.from(ids);
}

async function updateAnVILSource(sourcePath: string): Promise<void> {
  // Get existing platform studies and study ids from the NCPI source tsv.
  const [platformStudies, studyIds] = await getPlatformStudiesStudyIds(
    sourcePath,
    Platform.ANVIL
  );

  // Get AnVIL studies from API.
  const anvilIds = await fetchAnvilIds();

  // Update platform studies and report new studies for the specified platform.
  updatePlatformStudiesAndReportNewStudies(
    Platform.ANVIL,
    platformStudies,
    anvilIds,
    studyIds,
    sourcePath
  );
}

updateAnVILSource(sourcePath);
