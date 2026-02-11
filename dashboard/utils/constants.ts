export const PREMIUM_MAP: Record<string, number> = {
  "gsaauctions.gov": 0.00,
  "centurionservice.com": 19.00,
  "britishmedicalauctions.com": 20.00,
  "globalmedauctions.com": 19.00,
  "bidspotter.com": 20.00,
  "dotmed.com": 18.00,
  "mazree.com": 18.00,
  "govplanet.com": 18.00,
  "directbids.com": 15.00,
  "surplusmarketplace.com": 13.00,
  "gcsurplus.ca": 15.00,
  "greenpulse.health": 18.00,
  "troostwijkauctions.com": 0.00,
  "publicsurplus.com": 10.00,
  "purplewave.com": 10.00
}

export function getInitialPremium(url: string): number {
  const lowercaseUrl = url.toLowerCase()
  for (const [domain, percentage] of Object.entries(PREMIUM_MAP)) {
    if (lowercaseUrl.includes(domain)) {
      return percentage
    }
  }
  return 15.0 // Default fallback
}

export function getSiteKey(url: string): string {
  const lowercaseUrl = url.toLowerCase();
  if (lowercaseUrl.includes("gsaauctions.gov")) return "gsa";
  if (lowercaseUrl.includes("centurionservice.com")) return "centurion";
  if (lowercaseUrl.includes("bidspotter.com")) return "bidspotter";
  if (lowercaseUrl.includes("govplanet.com")) return "govplanet";
  if (lowercaseUrl.includes("purplewave.com")) return "purplewave";
  if (lowercaseUrl.includes("mazree.com")) return "mazree";
  if (lowercaseUrl.includes("directbids.com")) return "directbids";
  if (lowercaseUrl.includes("dotmed.com")) return "dotmed";
  if (lowercaseUrl.includes("britishmedicalauctions.com")) return "bma";
  if (lowercaseUrl.includes("surplusmarketplace.com")) return "surplusmarketplace";
  if (lowercaseUrl.includes("globalmedauctions.com")) return "globalmed";
  if (lowercaseUrl.includes("gcsurplus.ca")) return "gcsurplus";
  if (lowercaseUrl.includes("publicsurplus.com")) return "publicsurplus";
  if (lowercaseUrl.includes("troostwijkauctions.com")) return "troostwijk";
  if (lowercaseUrl.includes("greenpulse.health")) return "greenpulse";
  return "mock"; // Default fallback
}
