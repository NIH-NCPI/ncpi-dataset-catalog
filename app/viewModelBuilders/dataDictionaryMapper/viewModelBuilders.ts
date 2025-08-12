import { Attribute } from "./types";
import {
  DataDictionary,
  Attribute as BaseAttribute,
} from "@databiosphere/findable-ui/lib/common/entities";
import { LABEL } from "@databiosphere/findable-ui/lib/apis/azul/common/entities";

/**
 * Returns the source attribute for a given attribute with proper labeling and URL.
 * Currently supports dbgap and ncpi source types, and allows empty (i.e. no link) source
 * values.
 *
 * @param dataDictionary - The data dictionary containing annotations and prefixes.
 * @param attribute - The attribute to build the source for.
 * @returns A source object with label and URL or empty values if no valid source is found.
 */
export function buildSourceAttribute(
  dataDictionary: DataDictionary,
  attribute: BaseAttribute
): Attribute["source"] {
  const { annotations, prefixes } = dataDictionary;
  const attributeAnnotations = attribute.annotations;
  const defaultSource = { children: LABEL.NONE, href: "" };

  // Guard clause: check for required values.
  if (
    !annotations ||
    !prefixes ||
    Object.keys(annotations).length === 0 ||
    Object.keys(prefixes).length === 0 ||
    !attributeAnnotations
  ) {
    return defaultSource;
  }

  // Determine the supported source keys.
  const supportedKeys = ["dbgap", "ncpi"];

  // Find the first valid sourceKey where all required data is available
  const sourceKey = supportedKeys.find(
    (key) => annotations[key] && prefixes[key] && key in attributeAnnotations // Check if the key exists (allows empty strings)
  );

  // If no valid sourceKey is found, return default.
  if (!sourceKey) {
    return defaultSource;
  }

  // Build the appropriate source based on the key type.
  if (sourceKey === "dbgap") {
    const attributeValue = attributeAnnotations[sourceKey];
    return {
      children: annotations[sourceKey],
      href: attributeValue ? `${prefixes[sourceKey]}-${attributeValue}` : "",
    };
  }

  // No URL for ncpi source.
  return {
    children: annotations[sourceKey],
    href: "",
  };
}
