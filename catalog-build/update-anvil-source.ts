import fetch from "node-fetch";
import { DbGapId } from "../app/apis/catalog/ncpi-catalog/common/entities";
import { Platform } from "./constants";
import {
  getPlatformStudiesStudyIds,
  sourcePath,
  updatePlatformStudiesAndReportNewStudies,
} from "./utils";

interface AnvilDatasetsResponse {
  hits: Array<{
    datasets: Array<{
      registered_identifier: (string | null)[];
    }>;
  }>;
  pagination: {
    next: string | null;
  };
}

async function fetchAnvilPage(
  url: string,
  dbGapIds: Set<DbGapId>
): Promise<string | null> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  const data = (await response.json()) as AnvilDatasetsResponse;

  // Process each dataset
  for (const hit of data.hits) {
    for (const dataset of hit.datasets) {
      for (const id of dataset.registered_identifier) {
        // TODO how do we want to handle values such as "phs000744.v5.p2"?
        if (id && id.startsWith("phs")) {
          dbGapIds.add(id);
        }
      }
    }
  }

  return data.pagination.next;
}

async function fetchAnvilIds(): Promise<DbGapId[]> {
  const dbGapIds = new Set<DbGapId>();
  let url: string | null =
    "https://service.explore.anvilproject.org/index/datasets?size=25&catalog=anvil8";

  while (url) {
    // Add the IDs from the page and get the next page URL.
    url = await fetchAnvilPage(url, dbGapIds);
  }

  return Array.from(dbGapIds);
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
