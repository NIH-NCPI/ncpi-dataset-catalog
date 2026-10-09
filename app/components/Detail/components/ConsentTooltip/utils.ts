/**
 * Returns the consent long name to display, or undefined when it is missing or
 * a catalog build placeholder ("Unspecified", or an "ERROR: ..." message).
 * @param consentLongName - Consent long name.
 * @returns Consent long name, or undefined.
 */
export function getDisplayConsentLongName(
  consentLongName?: string
): string | undefined {
  if (!consentLongName || /^unspecified$|^error/i.test(consentLongName)) return;
  return consentLongName;
}
