export const PREMIUM_MAP: Record<string, number> = {
  "gsaauctions.gov": 0.00,
  "centurionservice.com": 19.00,
  "britishmedicalauctions.com": 20.00,
  "globalmedauctions.com": 19.00,
  "bidspotter.com": 15.00,
  "dotmed.com": 18.00,
  "mazree.com": 18.00,
  "govplanet.com": 18.00,
  "directbids.com": 15.00,
  "surplusmarketplace.com": 13.00,
  "gcsurplus.ca": 15.00,
  "greenpulse.health": 18.00,
  "troostwijkauctions.com": 0.00,
  "publicsurplus.com": 10.00,
  "purplewave.com": 10.00,
  "allsurplus.com": 12.50,
  "equipnet.com": 15.00
}

export const SUPPORTED_DOMAINS = Object.keys(PREMIUM_MAP);

export function getInitialPremium(url: string): number {
  let hostname = "";
  try {
    const parsed = new URL(url);
    hostname = parsed.hostname.toLowerCase();
  } catch {
    hostname = "";
  }

  for (const [domain, percentage] of Object.entries(PREMIUM_MAP)) {
    const lowerDomain = domain.toLowerCase();
    if (hostname === lowerDomain || hostname.endsWith("." + lowerDomain)) {
      return percentage;
    }
  }
  return 15.0; // Default fallback
}

export function getSiteKey(url: string): string {
  let hostname = "";
  try {
    const parsed = new URL(url);
    hostname = parsed.hostname.toLowerCase();
  } catch {
    hostname = url.toLowerCase();
  }

  if (hostname === "gsaauctions.gov" || hostname.endsWith(".gsaauctions.gov")) return "gsa";
  if (hostname === "centurionservice.com" || hostname.endsWith(".centurionservice.com")) return "centurion";
  if (hostname === "bidspotter.com" || hostname.endsWith(".bidspotter.com")) return "bidspotter";
  if (hostname === "govplanet.com" || hostname.endsWith(".govplanet.com")) return "govplanet";
  if (hostname === "purplewave.com" || hostname.endsWith(".purplewave.com")) return "purplewave";
  if (hostname === "mazree.com" || hostname.endsWith(".mazree.com")) return "mazree";
  if (hostname === "directbids.com" || hostname.endsWith(".directbids.com")) return "directbids";
  if (hostname === "dotmed.com" || hostname.endsWith(".dotmed.com")) return "dotmed";
  if (hostname === "britishmedicalauctions.com" || hostname.endsWith(".britishmedicalauctions.com")) return "bma";
  if (hostname === "surplusmarketplace.com" || hostname.endsWith(".surplusmarketplace.com")) return "surplusmarketplace";
  if (hostname === "globalmedauctions.com" || hostname.endsWith(".globalmedauctions.com")) return "globalmed";
  if (hostname === "gcsurplus.ca" || hostname.endsWith(".gcsurplus.ca")) return "gcsurplus";
  if (hostname === "publicsurplus.com" || hostname.endsWith(".publicsurplus.com")) return "publicsurplus";
  if (hostname === "troostwijkauctions.com" || hostname.endsWith(".troostwijkauctions.com")) return "troostwijk";
  if (hostname === "greenpulse.health" || hostname.endsWith(".greenpulse.health")) return "greenpulse";
  if (hostname === "allsurplus.com" || hostname.endsWith(".allsurplus.com")) return "allsurplus";
  if (hostname === "equipnet.com" || hostname.endsWith(".equipnet.com")) return "equipnet";
  return "mock"; // Default fallback
}
