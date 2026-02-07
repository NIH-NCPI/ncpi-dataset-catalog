/**
 * Downloads var_report.xml files from dbGaP FTP for all studies.
 * Files are saved to catalog-build/source/dbgap-variables/ (git-ignored).
 *
 * Run with: npx esrun catalog-build/download-dbgap-variables.ts
 *
 * Options:
 *   --limit N     Only download first N studies (for testing)
 *   --resume      Skip studies that already have downloaded files
 */

import fetch from "node-fetch";
import * as fs from "fs";
import * as path from "path";

const FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies";
const OUTPUT_DIR = path.join(__dirname, "source/dbgap-variables");

// Rate limiting settings
const DELAY_BETWEEN_STUDIES = 200; // ms between studies
const DELAY_BETWEEN_FILES = 50; // ms between file downloads

/**
 * Fetches the list of all study IDs from the FTP directory.
 * @returns Array of phs IDs.
 */
async function fetchAllStudyIds(): Promise<string[]> {
  console.log("Fetching study list from FTP...");
  const response = await fetch(`${FTP_BASE}/`);
  const html = await response.text();

  const matches = html.match(/phs\d+/g) || [];
  const uniqueIds = [...new Set(matches)].sort();
  console.log(`Found ${uniqueIds.length} studies on FTP`);
  return uniqueIds;
}

/**
 * Gets the latest version directory for a study.
 * @param phsId - Study ID.
 * @returns Latest version path or null if not found.
 */
async function getLatestVersion(phsId: string): Promise<string | null> {
  const response = await fetch(`${FTP_BASE}/${phsId}/`);
  if (!response.ok) return null;

  const html = await response.text();
  const versionPattern = new RegExp(`${phsId}\\.v(\\d+)\\.p(\\d+)`, "g");
  const matches = [...html.matchAll(versionPattern)];

  if (matches.length === 0) return null;

  let maxVersion = 0;
  let latestDir = "";
  for (const match of matches) {
    const version = parseInt(match[1]);
    if (version > maxVersion) {
      maxVersion = version;
      latestDir = match[0];
    }
  }

  return latestDir;
}

/**
 * Lists var_report.xml files in a study's pheno_variable_summaries directory.
 * @param phsId - Study ID.
 * @param version - Version string (e.g., "phs000001.v3.p1").
 * @returns Array of file names.
 */
async function listVarReportFiles(
  phsId: string,
  version: string
): Promise<string[]> {
  const url = `${FTP_BASE}/${phsId}/${version}/pheno_variable_summaries/`;
  const response = await fetch(url);
  if (!response.ok) return [];

  const html = await response.text();
  const matches = html.match(/href="([^"]*var_report\.xml)"/g) || [];

  return matches
    .map((m) => {
      const match = m.match(/href="([^"]+)"/);
      return match ? match[1] : "";
    })
    .filter(Boolean);
}

/**
 * Downloads a single file and saves it locally.
 * @param url - URL to download.
 * @param outputPath - Local file path.
 * @returns True if successful.
 */
async function downloadFile(url: string, outputPath: string): Promise<boolean> {
  try {
    const response = await fetch(url);
    if (!response.ok) return false;

    const content = await response.text();
    fs.writeFileSync(outputPath, content);
    return true;
  } catch {
    return false;
  }
}

/**
 * Downloads all var_report.xml files for a study.
 * @param phsId - Study ID.
 * @param resume - Skip if files already exist.
 * @returns Number of files downloaded.
 */
async function downloadStudyVariables(
  phsId: string,
  resume: boolean
): Promise<{ downloaded: number; skipped: number; total: number }> {
  const studyDir = path.join(OUTPUT_DIR, phsId);

  // Check if already downloaded (resume mode)
  if (resume && fs.existsSync(studyDir)) {
    const existing = fs.readdirSync(studyDir).filter((f) => f.endsWith(".xml"));
    if (existing.length > 0) {
      return {
        downloaded: 0,
        skipped: existing.length,
        total: existing.length,
      };
    }
  }

  // Get latest version
  const version = await getLatestVersion(phsId);
  if (!version) {
    return { downloaded: 0, skipped: 0, total: 0 };
  }

  // List var_report files
  const files = await listVarReportFiles(phsId, version);
  if (files.length === 0) {
    return { downloaded: 0, skipped: 0, total: 0 };
  }

  // Create output directory
  if (!fs.existsSync(studyDir)) {
    fs.mkdirSync(studyDir, { recursive: true });
  }

  // Download each file
  let downloaded = 0;
  for (const fileName of files) {
    const url = `${FTP_BASE}/${phsId}/${version}/pheno_variable_summaries/${fileName}`;
    const outputPath = path.join(studyDir, fileName);

    if (resume && fs.existsSync(outputPath)) {
      continue;
    }

    const success = await downloadFile(url, outputPath);
    if (success) {
      downloaded++;
    }

    await new Promise((r) => setTimeout(r, DELAY_BETWEEN_FILES));
  }

  return { downloaded, skipped: 0, total: files.length };
}

interface CliArgs {
  limit: number | undefined;
  resume: boolean;
}

/**
 * Parses command line arguments.
 * @returns Parsed CLI arguments.
 */
function parseArgs(): CliArgs {
  const args = process.argv.slice(2);
  const limitIdx = args.indexOf("--limit");
  return {
    limit: limitIdx >= 0 ? parseInt(args[limitIdx + 1]) : undefined,
    resume: args.includes("--resume"),
  };
}

/**
 * Calculates total disk usage of downloaded files.
 * @returns Total size in bytes.
 */
function calculateDiskUsage(): number {
  let totalSize = 0;
  const studyDirs = fs.readdirSync(OUTPUT_DIR);
  for (const dir of studyDirs) {
    const studyPath = path.join(OUTPUT_DIR, dir);
    if (fs.statSync(studyPath).isDirectory()) {
      const files = fs.readdirSync(studyPath);
      for (const file of files) {
        totalSize += fs.statSync(path.join(studyPath, file)).size;
      }
    }
  }
  return totalSize;
}

/**
 * Logs progress for a study download result.
 * @param progress - Progress string like "[1/100]".
 * @param phsId - Study ID.
 * @param result - Download result object.
 * @param result.downloaded - Number of files downloaded.
 * @param result.skipped - Number of files skipped.
 * @param result.total - Total number of files.
 * @param index - Current index in loop.
 */
function logProgress(
  progress: string,
  phsId: string,
  result: { downloaded: number; skipped: number; total: number },
  index: number
): void {
  if (result.total === 0) {
    if (index % 100 === 0) {
      console.log(`${progress} ${phsId}: No variable data`);
    }
    return;
  }
  if (result.downloaded > 0) {
    console.log(
      `${progress} ${phsId}: Downloaded ${result.downloaded}/${result.total} files`
    );
  } else if (result.skipped > 0) {
    console.log(`${progress} ${phsId}: Skipped (${result.skipped} existing)`);
  }
}

/**
 * Main download function.
 */
async function main(): Promise<void> {
  const { limit, resume } = parseArgs();

  console.log("=== dbGaP Variable Report Downloader ===\n");
  console.log(`Output directory: ${OUTPUT_DIR}`);
  console.log(`Resume mode: ${resume}`);
  if (limit) console.log(`Limit: ${limit} studies`);
  console.log("");

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const allIds = await fetchAllStudyIds();
  const studyIds = limit ? allIds.slice(0, limit) : allIds;

  console.log(`\nDownloading variables for ${studyIds.length} studies...\n`);

  const stats = {
    errors: 0,
    studiesWithData: 0,
    totalDownloaded: 0,
    totalFiles: 0,
    totalSkipped: 0,
  };

  for (let i = 0; i < studyIds.length; i++) {
    const phsId = studyIds[i];
    const progress = `[${i + 1}/${studyIds.length}]`;

    try {
      const result = await downloadStudyVariables(phsId, resume);
      if (result.total > 0) {
        stats.studiesWithData++;
        stats.totalFiles += result.total;
        stats.totalDownloaded += result.downloaded;
        stats.totalSkipped += result.skipped;
      }
      logProgress(progress, phsId, result, i);
    } catch (error) {
      stats.errors++;
      console.log(`${progress} ${phsId}: ERROR - ${error}`);
    }

    await new Promise((r) => setTimeout(r, DELAY_BETWEEN_STUDIES));
  }

  console.log("\n=== DOWNLOAD COMPLETE ===\n");
  console.log(`Studies processed: ${studyIds.length}`);
  console.log(`Studies with variable data: ${stats.studiesWithData}`);
  console.log(`Total var_report files: ${stats.totalFiles}`);
  console.log(`Files downloaded: ${stats.totalDownloaded}`);
  console.log(`Files skipped (existing): ${stats.totalSkipped}`);
  console.log(`Errors: ${stats.errors}`);

  const totalSize = calculateDiskUsage();
  console.log(`Total disk usage: ${(totalSize / 1024 / 1024).toFixed(1)} MB`);
}

main().catch(console.error);
