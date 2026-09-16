// ── Investor Eye — place gazetteer ───────────────────────────────────────────
// A compact gazetteer of places that MATTER TO MARKETS: major cities, ports,
// chokepoints, canals, straits, and industrial/energy regions.
//
// Why this exists: GDELT and USGS carry precise coordinates, but news-derived
// events have only a country (and often just a region label), so they were
// plotted at the country CENTROID — which put "United States" pins in Kansas and
// made the map look wrong. Resolving a named place from the headline anchors the
// event where it actually happened.
//
// Deliberately curated, not a dump of every city on earth: a wrong-but-precise
// pin is worse than an honest country centroid, so only unambiguous, high-signal
// places are listed, and matching is word-boundary based.
//
// Coordinates are approximate city/feature centres (good to a few km) — enough
// for a world map, and the UI reports the resolution method so precision is
// never overstated.

export type PlaceKind = 'city' | 'port' | 'chokepoint' | 'industrial' | 'energy';

export interface Place {
  /** Canonical display name. */
  name: string;
  /** ISO2 of the country the place sits in (or is governed by). */
  iso2: string;
  lon: number;
  lat: number;
  kind: PlaceKind;
  /** Lower-case alternative names / spellings / local names. */
  aliases?: string[];
  /** Higher wins when two places match the same text. */
  weight?: number;
}

/**
 * Curated places. Prioritised by market relevance: financial centres, major
 * ports, energy/industrial hubs, and shipping chokepoints (which drive the
 * "logistics disruption" story more than any single city).
 */
export const PLACES: Place[] = [
  // ── Chokepoints & canals (highest signal — these move freight rates) ──
  { name: 'Strait of Hormuz', iso2: 'IR', lon: 56.25, lat: 26.57, kind: 'chokepoint', weight: 90, aliases: ['hormuz', 'strait of hormuz'] },
  { name: 'Suez Canal', iso2: 'EG', lon: 32.35, lat: 30.6, kind: 'chokepoint', weight: 90, aliases: ['suez', 'suez canal', 'ismailia'] },
  { name: 'Bab-el-Mandeb', iso2: 'YE', lon: 43.33, lat: 12.58, kind: 'chokepoint', weight: 88, aliases: ['bab el mandeb', 'bab-el-mandeb', 'mandeb'] },
  { name: 'Panama Canal', iso2: 'PA', lon: -79.58, lat: 9.08, kind: 'chokepoint', weight: 88, aliases: ['panama canal', 'gatun'] },
  { name: 'Strait of Malacca', iso2: 'MY', lon: 100.5, lat: 2.5, kind: 'chokepoint', weight: 88, aliases: ['malacca', 'strait of malacca', 'malacca strait'] },
  { name: 'Bosphorus', iso2: 'TR', lon: 29.05, lat: 41.12, kind: 'chokepoint', weight: 84, aliases: ['bosphorus', 'bosporus', 'istanbul strait'] },
  { name: 'Turkish Straits', iso2: 'TR', lon: 26.7, lat: 40.35, kind: 'chokepoint', weight: 82, aliases: ['dardanelles', 'canakkale'] },
  { name: 'Taiwan Strait', iso2: 'TW', lon: 119.5, lat: 24.5, kind: 'chokepoint', weight: 86, aliases: ['taiwan strait'] },
  { name: 'Strait of Gibraltar', iso2: 'ES', lon: -5.6, lat: 35.95, kind: 'chokepoint', weight: 80, aliases: ['gibraltar'] },
  { name: 'Danish Straits', iso2: 'DK', lon: 12.6, lat: 55.7, kind: 'chokepoint', weight: 76, aliases: ['oresund', 'kattegat'] },
  { name: 'Red Sea', iso2: 'SA', lon: 39.0, lat: 20.0, kind: 'chokepoint', weight: 84, aliases: ['red sea'] },
  { name: 'Black Sea', iso2: 'RO', lon: 34.0, lat: 43.5, kind: 'chokepoint', weight: 78, aliases: ['black sea'] },
  { name: 'Cape of Good Hope', iso2: 'ZA', lon: 18.47, lat: -34.36, kind: 'chokepoint', weight: 74, aliases: ['cape of good hope'] },

  // ── Major ports ──
  { name: 'Rotterdam', iso2: 'NL', lon: 4.48, lat: 51.92, kind: 'port', weight: 80, aliases: ['rotterdam', 'port of rotterdam'] },
  { name: 'Antwerp', iso2: 'BE', lon: 4.4, lat: 51.22, kind: 'port', weight: 74, aliases: ['antwerp', 'antwerpen'] },
  { name: 'Hamburg', iso2: 'DE', lon: 9.99, lat: 53.55, kind: 'port', weight: 74 },
  { name: 'Shanghai', iso2: 'CN', lon: 121.47, lat: 31.23, kind: 'port', weight: 84, aliases: ['shanghai', 'yangshan'] },
  { name: 'Shenzhen', iso2: 'CN', lon: 114.06, lat: 22.54, kind: 'port', weight: 78 },
  { name: 'Ningbo', iso2: 'CN', lon: 121.55, lat: 29.87, kind: 'port', weight: 74, aliases: ['ningbo', 'zhoushan'] },
  { name: 'Singapore', iso2: 'SG', lon: 103.85, lat: 1.29, kind: 'port', weight: 86, aliases: ['singapore'] },
  { name: 'Busan', iso2: 'KR', lon: 129.04, lat: 35.1, kind: 'port', weight: 76 },
  { name: 'Jebel Ali', iso2: 'AE', lon: 55.03, lat: 25.0, kind: 'port', weight: 78, aliases: ['jebel ali', 'jebel ali port'] },
  { name: 'Port of Jeddah', iso2: 'SA', lon: 39.16, lat: 21.48, kind: 'port', weight: 72, aliases: ['jeddah', 'jiddah'] },
  { name: 'Port Said', iso2: 'EG', lon: 32.3, lat: 31.26, kind: 'port', weight: 72, aliases: ['port said'] },
  { name: 'Los Angeles', iso2: 'US', lon: -118.24, lat: 34.05, kind: 'port', weight: 78, aliases: ['los angeles', 'long beach'] },
  { name: 'New York', iso2: 'US', lon: -74.01, lat: 40.71, kind: 'port', weight: 80, aliases: ['new york', 'new york city', 'nyc', 'newark'] },
  { name: 'Houston', iso2: 'US', lon: -95.37, lat: 29.76, kind: 'port', weight: 76, aliases: ['houston'] },
  { name: 'Santos', iso2: 'BR', lon: -46.33, lat: -23.96, kind: 'port', weight: 70 },
  { name: 'Durban', iso2: 'ZA', lon: 31.02, lat: -29.86, kind: 'port', weight: 66 },
  { name: 'Mumbai', iso2: 'IN', lon: 72.88, lat: 19.08, kind: 'port', weight: 74, aliases: ['mumbai', 'bombay'] },
  { name: 'Chennai', iso2: 'IN', lon: 80.27, lat: 13.08, kind: 'port', weight: 66 },
  { name: 'Port Klang', iso2: 'MY', lon: 101.36, lat: 3.0, kind: 'port', weight: 68, aliases: ['port klang', 'klang'] },
  { name: 'Laem Chabang', iso2: 'TH', lon: 100.89, lat: 13.08, kind: 'port', weight: 64 },
  { name: 'Kaohsiung', iso2: 'TW', lon: 120.31, lat: 22.62, kind: 'port', weight: 68 },
  { name: 'Vladivostok', iso2: 'RU', lon: 131.89, lat: 43.12, kind: 'port', weight: 66 },
  { name: 'Odessa', iso2: 'UA', lon: 30.72, lat: 46.48, kind: 'port', weight: 74, aliases: ['odesa', 'odessa'] },
  { name: 'Constanta', iso2: 'RO', lon: 28.65, lat: 44.17, kind: 'port', weight: 62 },
  { name: 'Haifa', iso2: 'IL', lon: 34.99, lat: 32.82, kind: 'port', weight: 70, aliases: ['haifa'] },
  { name: 'Ashkelon', iso2: 'IL', lon: 34.57, lat: 31.67, kind: 'port', weight: 66 },
  { name: 'Port of Karachi', iso2: 'PK', lon: 66.99, lat: 24.84, kind: 'port', weight: 70, aliases: ['karachi', 'port qasim'] },
  { name: 'Port of Gwadar', iso2: 'PK', lon: 62.33, lat: 25.12, kind: 'port', weight: 68, aliases: ['gwadar'] },
  { name: 'Colombo', iso2: 'LK', lon: 79.85, lat: 6.93, kind: 'port', weight: 64 },
  { name: 'Melbourne', iso2: 'AU', lon: 144.96, lat: -37.81, kind: 'port', weight: 64 },
  { name: 'Sydney', iso2: 'AU', lon: 151.21, lat: -33.87, kind: 'city', weight: 70 },

  // ── Financial centres ──
  { name: 'London', iso2: 'GB', lon: -0.13, lat: 51.51, kind: 'city', weight: 84, aliases: ['london', 'city of london'] },
  { name: 'Washington', iso2: 'US', lon: -77.04, lat: 38.91, kind: 'city', weight: 82, aliases: ['washington', 'washington dc', 'washington d.c.'] },
  { name: 'Brussels', iso2: 'BE', lon: 4.35, lat: 50.85, kind: 'city', weight: 78, aliases: ['brussels', 'bruxelles'] },
  { name: 'Frankfurt', iso2: 'DE', lon: 8.68, lat: 50.11, kind: 'city', weight: 76, aliases: ['frankfurt'] },
  { name: 'Zurich', iso2: 'CH', lon: 8.54, lat: 47.38, kind: 'city', weight: 74 },
  { name: 'Geneva', iso2: 'CH', lon: 6.14, lat: 46.2, kind: 'city', weight: 74 },
  { name: 'Tokyo', iso2: 'JP', lon: 139.69, lat: 35.69, kind: 'city', weight: 84, aliases: ['tokyo'] },
  { name: 'Beijing', iso2: 'CN', lon: 116.41, lat: 39.9, kind: 'city', weight: 84, aliases: ['beijing', 'peking'] },
  { name: 'Hong Kong', iso2: 'HK', lon: 114.17, lat: 22.32, kind: 'city', weight: 80, aliases: ['hong kong'] },
  { name: 'Moscow', iso2: 'RU', lon: 37.62, lat: 55.76, kind: 'city', weight: 84, aliases: ['moscow', 'kremlin'] },
  { name: 'Kyiv', iso2: 'UA', lon: 30.52, lat: 50.45, kind: 'city', weight: 82, aliases: ['kyiv', 'kiev'] },
  { name: 'Tehran', iso2: 'IR', lon: 51.39, lat: 35.69, kind: 'city', weight: 80, aliases: ['tehran', 'teheran'] },
  { name: 'Tel Aviv', iso2: 'IL', lon: 34.78, lat: 32.08, kind: 'city', weight: 76, aliases: ['tel aviv'] },
  { name: 'Jerusalem', iso2: 'IL', lon: 35.21, lat: 31.77, kind: 'city', weight: 76 },
  { name: 'Gaza', iso2: 'PS', lon: 34.47, lat: 31.5, kind: 'city', weight: 80, aliases: ['gaza', 'gaza strip'] },
  { name: 'Beirut', iso2: 'LB', lon: 35.5, lat: 33.89, kind: 'city', weight: 72 },
  { name: 'Damascus', iso2: 'SY', lon: 36.29, lat: 33.51, kind: 'city', weight: 72 },
  { name: 'Baghdad', iso2: 'IQ', lon: 44.36, lat: 33.31, kind: 'city', weight: 72 },
  { name: 'Riyadh', iso2: 'SA', lon: 46.72, lat: 24.71, kind: 'city', weight: 74, aliases: ['riyadh'] },
  { name: 'Abu Dhabi', iso2: 'AE', lon: 54.37, lat: 24.45, kind: 'city', weight: 72, aliases: ['abu dhabi'] },
  { name: 'Dubai', iso2: 'AE', lon: 55.27, lat: 25.2, kind: 'city', weight: 74, aliases: ['dubai'] },
  { name: 'Doha', iso2: 'QA', lon: 51.53, lat: 25.29, kind: 'city', weight: 70, aliases: ['doha'] },
  { name: 'Sanaa', iso2: 'YE', lon: 44.21, lat: 15.37, kind: 'city', weight: 66, aliases: ['sanaa', "sana'a"] },
  { name: 'Aden', iso2: 'YE', lon: 45.04, lat: 12.79, kind: 'port', weight: 70, aliases: ['aden'] },
  { name: 'New Delhi', iso2: 'IN', lon: 77.21, lat: 28.61, kind: 'city', weight: 80, aliases: ['new delhi', 'delhi'] },
  { name: 'Islamabad', iso2: 'PK', lon: 73.06, lat: 33.69, kind: 'city', weight: 72, aliases: ['islamabad'] },
  { name: 'Rawalpindi', iso2: 'PK', lon: 73.05, lat: 33.6, kind: 'city', weight: 62 },
  { name: 'Lahore', iso2: 'PK', lon: 74.34, lat: 31.55, kind: 'city', weight: 64 },
  { name: 'Taipei', iso2: 'TW', lon: 121.56, lat: 25.03, kind: 'city', weight: 78, aliases: ['taipei'] },
  { name: 'Seoul', iso2: 'KR', lon: 126.98, lat: 37.57, kind: 'city', weight: 76, aliases: ['seoul'] },
  { name: 'Pyongyang', iso2: 'KP', lon: 125.75, lat: 39.03, kind: 'city', weight: 66, aliases: ['pyongyang'] },
  { name: 'Canberra', iso2: 'AU', lon: 149.13, lat: -35.28, kind: 'city', weight: 64 },
  { name: 'Ottawa', iso2: 'CA', lon: -75.7, lat: 45.42, kind: 'city', weight: 64 },
  { name: 'Brasilia', iso2: 'BR', lon: -47.88, lat: -15.79, kind: 'city', weight: 66, aliases: ['brasilia', 'brasília'] },
  { name: 'Buenos Aires', iso2: 'AR', lon: -58.38, lat: -34.6, kind: 'city', weight: 68 },
  { name: 'Caracas', iso2: 'VE', lon: -66.9, lat: 10.48, kind: 'city', weight: 68, aliases: ['caracas'] },
  { name: 'Cairo', iso2: 'EG', lon: 31.24, lat: 30.04, kind: 'city', weight: 74, aliases: ['cairo'] },
  { name: 'Ankara', iso2: 'TR', lon: 32.86, lat: 39.93, kind: 'city', weight: 72, aliases: ['ankara'] },
  { name: 'Vienna', iso2: 'AT', lon: 16.37, lat: 48.21, kind: 'city', weight: 70 },
  { name: 'Paris', iso2: 'FR', lon: 2.35, lat: 48.86, kind: 'city', weight: 78, aliases: ['paris'] },
  { name: 'Berlin', iso2: 'DE', lon: 13.4, lat: 52.52, kind: 'city', weight: 76, aliases: ['berlin'] },
  { name: 'Warsaw', iso2: 'PL', lon: 21.01, lat: 52.23, kind: 'city', weight: 70 },
  { name: 'Amsterdam', iso2: 'NL', lon: 4.9, lat: 52.37, kind: 'city', weight: 70 },

  // ── Energy / industrial regions ──
  { name: 'Abqaiq', iso2: 'SA', lon: 49.68, lat: 25.94, kind: 'energy', weight: 82, aliases: ['abqaiq'] },
  { name: 'Ras Tanura', iso2: 'SA', lon: 50.16, lat: 26.65, kind: 'energy', weight: 80, aliases: ['ras tanura'] },
  { name: 'Kharg Island', iso2: 'IR', lon: 50.32, lat: 29.26, kind: 'energy', weight: 78, aliases: ['kharg'] },
  { name: 'Basra', iso2: 'IQ', lon: 47.78, lat: 30.51, kind: 'energy', weight: 76, aliases: ['basra', 'basrah'] },
  { name: 'Kirkuk', iso2: 'IQ', lon: 44.39, lat: 35.47, kind: 'energy', weight: 72, aliases: ['kirkuk'] },
  { name: 'Ruwais', iso2: 'AE', lon: 52.73, lat: 24.11, kind: 'energy', weight: 70, aliases: ['ruwais'] },
  { name: 'Ras Laffan', iso2: 'QA', lon: 51.55, lat: 25.91, kind: 'energy', weight: 76, aliases: ['ras laffan'] },
  { name: 'Novorossiysk', iso2: 'RU', lon: 37.78, lat: 44.72, kind: 'energy', weight: 76, aliases: ['novorossiysk'] },
  { name: 'Primorsk', iso2: 'RU', lon: 28.61, lat: 60.36, kind: 'energy', weight: 70, aliases: ['primorsk'] },
  { name: 'Ust-Luga', iso2: 'RU', lon: 28.6, lat: 59.66, kind: 'energy', weight: 70, aliases: ['ust-luga', 'ust luga'] },
  { name: 'Yanbu', iso2: 'SA', lon: 38.06, lat: 24.09, kind: 'energy', weight: 70, aliases: ['yanbu'] },
  { name: 'Cushing', iso2: 'US', lon: -96.77, lat: 35.98, kind: 'energy', weight: 74, aliases: ['cushing'] },
  { name: 'Permian Basin', iso2: 'US', lon: -102.5, lat: 31.9, kind: 'energy', weight: 72, aliases: ['permian', 'permian basin', 'midland'] },
  { name: 'Baytown', iso2: 'US', lon: -94.98, lat: 29.74, kind: 'energy', weight: 68, aliases: ['baytown'] },
  { name: 'Norilsk', iso2: 'RU', lon: 88.2, lat: 69.35, kind: 'industrial', weight: 70, aliases: ['norilsk'] },
  { name: 'Jubail', iso2: 'SA', lon: 49.66, lat: 27.0, kind: 'industrial', weight: 70, aliases: ['jubail'] },
  { name: 'Fos-sur-Mer', iso2: 'FR', lon: 4.95, lat: 43.43, kind: 'industrial', weight: 64, aliases: ['fos-sur-mer', 'fos sur mer'] },
  { name: 'Duisburg', iso2: 'DE', lon: 6.76, lat: 51.43, kind: 'industrial', weight: 64 },
  { name: 'Zaporizhzhia', iso2: 'UA', lon: 35.14, lat: 47.84, kind: 'energy', weight: 76, aliases: ['zaporizhzhia', 'zaporizhia'] },
  { name: 'Kursk', iso2: 'RU', lon: 36.19, lat: 51.73, kind: 'energy', weight: 68, aliases: ['kursk'] },
  { name: 'Fukushima', iso2: 'JP', lon: 140.47, lat: 37.75, kind: 'energy', weight: 68, aliases: ['fukushima'] },
  { name: 'Taiwan Semiconductor', iso2: 'TW', lon: 120.97, lat: 24.77, kind: 'industrial', weight: 80, aliases: ['tsmc', 'hsinchu', 'tainan'] },
  { name: 'Rare Earth Belt', iso2: 'CN', lon: 110.0, lat: 40.6, kind: 'industrial', weight: 72, aliases: ['baotou', 'inner mongolia'] },
  { name: 'Chuquicamata', iso2: 'CL', lon: -68.9, lat: -22.32, kind: 'industrial', weight: 70, aliases: ['chuquicamata', 'atacama'] },
  { name: 'Escondida', iso2: 'CL', lon: -69.07, lat: -24.27, kind: 'industrial', weight: 70, aliases: ['escondida'] },
  { name: 'Grasberg', iso2: 'ID', lon: 137.5, lat: -4.05, kind: 'industrial', weight: 68, aliases: ['grasberg', 'papua'] },
  { name: 'Witwatersrand', iso2: 'ZA', lon: 27.9, lat: -26.2, kind: 'industrial', weight: 66, aliases: ['witwatersrand', 'johannesburg'] },
  { name: 'Ruhr', iso2: 'DE', lon: 7.1, lat: 51.45, kind: 'industrial', weight: 68, aliases: ['ruhr', 'essen'] },
  { name: 'Pilbara', iso2: 'AU', lon: 118.5, lat: -22.0, kind: 'industrial', weight: 68, aliases: ['pilbara'] },

  // ── Second pass: gaps found by probing real headlines ──────────────────
  // Mineral / energy regions whose names appear in commodity-supply stories.
  { name: 'Antofagasta', iso2: 'CL', lon: -70.40, lat: -23.65, kind: 'industrial', weight: 68, aliases: ['antofagasta'] },
  { name: 'Salar de Atacama', iso2: 'CL', lon: -68.30, lat: -23.50, kind: 'industrial', weight: 70, aliases: ['salar de atacama', 'atacama salt'] },
  { name: 'Mount Isa', iso2: 'AU', lon: 139.49, lat: -20.73, kind: 'industrial', weight: 64, aliases: ['mount isa'] },
  { name: 'Sudbury', iso2: 'CA', lon: -80.99, lat: 46.49, kind: 'industrial', weight: 64, aliases: ['sudbury'] },
  { name: 'Fort McMurray', iso2: 'CA', lon: -111.38, lat: 56.73, kind: 'energy', weight: 70, aliases: ['fort mcmurray', 'oil sands', 'athabasca'] },
  { name: 'Ras Ghareb', iso2: 'EG', lon: 33.08, lat: 28.36, kind: 'energy', weight: 64, aliases: ['ras ghareb'] },
  { name: 'Bonny Island', iso2: 'NG', lon: 7.17, lat: 4.42, kind: 'energy', weight: 68, aliases: ['bonny', 'bonny island'] },
  { name: 'Niger Delta', iso2: 'NG', lon: 6.0, lat: 5.0, kind: 'energy', weight: 72, aliases: ['niger delta', 'delta state'] },
  { name: 'Kashagan', iso2: 'KZ', lon: 51.5, lat: 46.5, kind: 'energy', weight: 68, aliases: ['kashagan', 'caspian pipeline'] },
  { name: 'Daqing', iso2: 'CN', lon: 125.0, lat: 46.6, kind: 'energy', weight: 70, aliases: ['daqing'] },
  { name: 'Ordos', iso2: 'CN', lon: 109.78, lat: 39.61, kind: 'energy', weight: 66, aliases: ['ordos'] },

  // ── Rivers / waterways that shape logistics stories ────────────────────
  { name: 'Danube', iso2: 'RO', lon: 29.60, lat: 45.20, kind: 'chokepoint', weight: 76, aliases: ['danube', 'danube river'] },
  { name: 'Rhine', iso2: 'DE', lon: 7.60, lat: 50.30, kind: 'chokepoint', weight: 70, aliases: ['rhine', 'rhine river'] },
  { name: 'Mississippi', iso2: 'US', lon: -90.10, lat: 35.15, kind: 'chokepoint', weight: 68, aliases: ['mississippi', 'lower mississippi'] },
  { name: 'Yangtze', iso2: 'CN', lon: 114.30, lat: 30.60, kind: 'chokepoint', weight: 70, aliases: ['yangtze', 'yangtze river'] },
  { name: 'Parana', iso2: 'AR', lon: -58.30, lat: -34.00, kind: 'chokepoint', weight: 66, aliases: ['parana', 'paraná', 'parana river'] },
  { name: 'Bosphorus Strait', iso2: 'TR', lon: 29.05, lat: 41.12, kind: 'chokepoint', weight: 82, aliases: ['bosphorus strait'] },

  // ── Additional cities that recur in policy and conflict coverage ───────
  { name: 'Nairobi', iso2: 'KE', lon: 36.82, lat: -1.29, kind: 'city', weight: 70, aliases: ['nairobi'] },
  { name: 'Lagos', iso2: 'NG', lon: 3.38, lat: 6.52, kind: 'city', weight: 70, aliases: ['lagos'] },
  { name: 'Khartoum', iso2: 'SD', lon: 32.53, lat: 15.55, kind: 'city', weight: 68, aliases: ['khartoum'] },
  { name: 'Kinshasa', iso2: 'CD', lon: 15.31, lat: -4.32, kind: 'city', weight: 66, aliases: ['kinshasa'] },
  { name: 'Addis Ababa', iso2: 'ET', lon: 38.75, lat: 9.03, kind: 'city', weight: 68, aliases: ['addis ababa'] },
  { name: 'Jakarta', iso2: 'ID', lon: 106.85, lat: -6.21, kind: 'city', weight: 72, aliases: ['jakarta'] },
  { name: 'Manila', iso2: 'PH', lon: 120.98, lat: 14.60, kind: 'city', weight: 70, aliases: ['manila'] },
  { name: 'Hanoi', iso2: 'VN', lon: 105.83, lat: 21.03, kind: 'city', weight: 68, aliases: ['hanoi'] },
  { name: 'Bogota', iso2: 'CO', lon: -74.07, lat: 4.71, kind: 'city', weight: 68, aliases: ['bogota', 'bogotá'] },
  { name: 'Santiago', iso2: 'CL', lon: -70.65, lat: -33.46, kind: 'city', weight: 68, aliases: ['santiago'] },
  { name: 'Lima', iso2: 'PE', lon: -77.04, lat: -12.05, kind: 'city', weight: 68, aliases: ['lima'] },
  { name: 'Bangkok', iso2: 'TH', lon: 100.50, lat: 13.76, kind: 'city', weight: 70, aliases: ['bangkok'] },
  { name: 'Kuala Lumpur', iso2: 'MY', lon: 101.69, lat: 3.14, kind: 'city', weight: 68, aliases: ['kuala lumpur'] },
  { name: 'Melbourne', iso2: 'AU', lon: 144.96, lat: -37.81, kind: 'city', weight: 66, aliases: ['melbourne'] },
  { name: 'Oslo', iso2: 'NO', lon: 10.75, lat: 59.91, kind: 'city', weight: 66, aliases: ['oslo'] },
  { name: 'Stockholm', iso2: 'SE', lon: 18.07, lat: 59.33, kind: 'city', weight: 66, aliases: ['stockholm'] },
  { name: 'Athens', iso2: 'GR', lon: 23.73, lat: 37.98, kind: 'city', weight: 66, aliases: ['athens'] },
  { name: 'Helsinki', iso2: 'FI', lon: 24.94, lat: 60.17, kind: 'city', weight: 64, aliases: ['helsinki'] },
  { name: 'Vienna', iso2: 'AT', lon: 16.37, lat: 48.21, kind: 'city', weight: 68, aliases: ['vienna', 'opec headquarters'] },
  { name: 'Prague', iso2: 'CZ', lon: 14.42, lat: 50.08, kind: 'city', weight: 64, aliases: ['prague'] },
  { name: 'Budapest', iso2: 'HU', lon: 19.04, lat: 47.50, kind: 'city', weight: 64, aliases: ['budapest'] },
  { name: 'Bucharest', iso2: 'RO', lon: 26.10, lat: 44.43, kind: 'city', weight: 64, aliases: ['bucharest'] },
  { name: 'Copenhagen', iso2: 'DK', lon: 12.57, lat: 55.68, kind: 'city', weight: 64, aliases: ['copenhagen'] },
  { name: 'Lisbon', iso2: 'PT', lon: -9.14, lat: 38.72, kind: 'city', weight: 64, aliases: ['lisbon'] },
  { name: 'Madrid', iso2: 'ES', lon: -3.70, lat: 40.42, kind: 'city', weight: 68, aliases: ['madrid'] },
  { name: 'Rome', iso2: 'IT', lon: 12.50, lat: 41.90, kind: 'city', weight: 68, aliases: ['rome'] },
  { name: 'Brasilia', iso2: 'BR', lon: -47.88, lat: -15.79, kind: 'city', weight: 70, aliases: ['brasilia', 'brasília'] },
  { name: 'Ottawa', iso2: 'CA', lon: -75.70, lat: 45.42, kind: 'city', weight: 66, aliases: ['ottawa'] },
  { name: 'Wellington', iso2: 'NZ', lon: 174.78, lat: -41.29, kind: 'city', weight: 64, aliases: ['wellington'] },
  { name: 'Auckland', iso2: 'NZ', lon: 174.76, lat: -36.85, kind: 'city', weight: 64, aliases: ['auckland'] },
  { name: 'Astana', iso2: 'KZ', lon: 71.43, lat: 51.13, kind: 'city', weight: 64, aliases: ['astana', 'nur-sultan'] },
  { name: 'Almaty', iso2: 'KZ', lon: 76.89, lat: 43.24, kind: 'city', weight: 64, aliases: ['almaty'] },
  { name: 'Kabul', iso2: 'AF', lon: 69.18, lat: 34.53, kind: 'city', weight: 68, aliases: ['kabul'] },
  { name: 'Dhaka', iso2: 'BD', lon: 90.41, lat: 23.81, kind: 'city', weight: 66, aliases: ['dhaka'] },
  { name: 'Kathmandu', iso2: 'NP', lon: 85.32, lat: 27.72, kind: 'city', weight: 62, aliases: ['kathmandu'] },
  { name: 'Muscat', iso2: 'OM', lon: 58.41, lat: 23.59, kind: 'city', weight: 64, aliases: ['muscat'] },
  { name: 'Kuwait City', iso2: 'KW', lon: 47.98, lat: 29.38, kind: 'city', weight: 68, aliases: ['kuwait city'] },
  { name: 'Mumbai', iso2: 'IN', lon: 72.88, lat: 19.08, kind: 'city', weight: 74, aliases: ['mumbai', 'bombay'] },
  { name: 'Bengaluru', iso2: 'IN', lon: 77.59, lat: 12.97, kind: 'city', weight: 66, aliases: ['bengaluru', 'bangalore'] },
  { name: 'Hyderabad', iso2: 'IN', lon: 78.49, lat: 17.39, kind: 'city', weight: 64, aliases: ['hyderabad'] },
  { name: 'Chennai', iso2: 'IN', lon: 80.27, lat: 13.08, kind: 'city', weight: 64, aliases: ['chennai', 'madras'] },
  { name: 'Kolkata', iso2: 'IN', lon: 88.36, lat: 22.57, kind: 'city', weight: 64, aliases: ['kolkata', 'calcutta'] },
  { name: 'Guangzhou', iso2: 'CN', lon: 113.26, lat: 23.13, kind: 'industrial', weight: 70, aliases: ['guangzhou', 'canton'] },
  { name: 'Tianjin', iso2: 'CN', lon: 117.20, lat: 39.13, kind: 'port', weight: 68, aliases: ['tianjin'] },
  { name: 'Qingdao', iso2: 'CN', lon: 120.38, lat: 36.07, kind: 'port', weight: 66, aliases: ['qingdao'] },
  { name: 'Dalian', iso2: 'CN', lon: 121.62, lat: 38.91, kind: 'port', weight: 66, aliases: ['dalian'] },
  { name: 'Xiamen', iso2: 'CN', lon: 118.09, lat: 24.48, kind: 'port', weight: 64, aliases: ['xiamen'] },
  { name: 'Yokohama', iso2: 'JP', lon: 139.64, lat: 35.44, kind: 'port', weight: 68, aliases: ['yokohama'] },
  { name: 'Nagoya', iso2: 'JP', lon: 136.91, lat: 35.18, kind: 'industrial', weight: 66, aliases: ['nagoya'] },
  { name: 'Osaka', iso2: 'JP', lon: 135.50, lat: 34.69, kind: 'industrial', weight: 66, aliases: ['osaka'] },
  { name: 'Ulsan', iso2: 'KR', lon: 129.31, lat: 35.54, kind: 'energy', weight: 68, aliases: ['ulsan'] },
  { name: 'Incheon', iso2: 'KR', lon: 126.71, lat: 37.46, kind: 'port', weight: 66, aliases: ['incheon'] },
  { name: 'Ho Chi Minh City', iso2: 'VN', lon: 106.63, lat: 10.82, kind: 'city', weight: 66, aliases: ['ho chi minh', 'saigon'] },
  { name: 'Batam', iso2: 'ID', lon: 104.03, lat: 1.13, kind: 'industrial', weight: 60, aliases: ['batam'] },
  { name: 'Port Harcourt', iso2: 'NG', lon: 7.01, lat: 4.78, kind: 'port', weight: 66, aliases: ['port harcourt'] },
  { name: 'Durban', iso2: 'ZA', lon: 31.02, lat: -29.86, kind: 'port', weight: 66, aliases: ['durban'] },
  { name: 'Cape Town', iso2: 'ZA', lon: 18.42, lat: -33.92, kind: 'port', weight: 68, aliases: ['cape town'] },
  { name: 'Mombasa', iso2: 'KE', lon: 39.67, lat: -4.04, kind: 'port', weight: 66, aliases: ['mombasa'] },
  { name: 'Djibouti', iso2: 'DJ', lon: 43.15, lat: 11.59, kind: 'port', weight: 70, aliases: ['djibouti', 'doraleh'] },
  { name: 'Berbera', iso2: 'SO', lon: 45.01, lat: 10.44, kind: 'port', weight: 62, aliases: ['berbera'] },
  { name: 'Massawa', iso2: 'ER', lon: 39.45, lat: 15.61, kind: 'port', weight: 60, aliases: ['massawa'] },
  { name: 'Aqaba', iso2: 'JO', lon: 35.00, lat: 29.53, kind: 'port', weight: 68, aliases: ['aqaba'] },
  { name: 'Alexandria', iso2: 'EG', lon: 29.92, lat: 31.20, kind: 'port', weight: 70, aliases: ['alexandria'] },
  { name: 'Benghazi', iso2: 'LY', lon: 20.07, lat: 32.12, kind: 'port', weight: 64, aliases: ['benghazi'] },
  { name: 'Algiers', iso2: 'DZ', lon: 3.06, lat: 36.75, kind: 'port', weight: 64, aliases: ['algiers'] },
  { name: 'Casablanca', iso2: 'MA', lon: -7.59, lat: 33.57, kind: 'port', weight: 64, aliases: ['casablanca'] },
  { name: 'Tanger Med', iso2: 'MA', lon: -5.50, lat: 35.89, kind: 'port', weight: 68, aliases: ['tanger med', 'tangier'] },
  { name: 'Piraeus', iso2: 'GR', lon: 23.63, lat: 37.94, kind: 'port', weight: 68, aliases: ['piraeus'] },
  { name: 'Gioia Tauro', iso2: 'IT', lon: 15.90, lat: 38.45, kind: 'port', weight: 62, aliases: ['gioia tauro'] },
  { name: 'Felixstowe', iso2: 'GB', lon: 1.33, lat: 51.96, kind: 'port', weight: 66, aliases: ['felixstowe'] },
  { name: 'Southampton', iso2: 'GB', lon: -1.40, lat: 50.90, kind: 'port', weight: 64, aliases: ['southampton'] },
  { name: 'Le Havre', iso2: 'FR', lon: 0.11, lat: 49.49, kind: 'port', weight: 66, aliases: ['le havre'] },
  { name: 'Marseille', iso2: 'FR', lon: 5.37, lat: 43.30, kind: 'port', weight: 66, aliases: ['marseille'] },
  { name: 'Barcelona', iso2: 'ES', lon: 2.17, lat: 41.39, kind: 'port', weight: 66, aliases: ['barcelona'] },
  { name: 'Valencia', iso2: 'ES', lon: -0.38, lat: 39.47, kind: 'port', weight: 66, aliases: ['valencia'] },
  { name: 'Genoa', iso2: 'IT', lon: 8.93, lat: 44.41, kind: 'port', weight: 66, aliases: ['genoa', 'genova'] },
  { name: 'Gdansk', iso2: 'PL', lon: 18.65, lat: 54.35, kind: 'port', weight: 64, aliases: ['gdansk', 'gdańsk'] },
  { name: 'Constanta', iso2: 'RO', lon: 28.65, lat: 44.17, kind: 'port', weight: 66, aliases: ['constanta', 'constanța'] },
  { name: 'Novorossiysk', iso2: 'RU', lon: 37.78, lat: 44.72, kind: 'port', weight: 72, aliases: ['novorossiysk'] },
  { name: 'St Petersburg', iso2: 'RU', lon: 30.31, lat: 59.94, kind: 'port', weight: 66, aliases: ['st petersburg', 'saint petersburg'] },
  { name: 'Murmansk', iso2: 'RU', lon: 33.09, lat: 68.97, kind: 'port', weight: 66, aliases: ['murmansk'] },
  { name: 'Vladivostok', iso2: 'RU', lon: 131.89, lat: 43.12, kind: 'port', weight: 68, aliases: ['vladivostok'] },
  { name: 'Vancouver', iso2: 'CA', lon: -123.12, lat: 49.28, kind: 'port', weight: 70, aliases: ['vancouver'] },
  { name: 'Montreal', iso2: 'CA', lon: -73.57, lat: 45.50, kind: 'port', weight: 66, aliases: ['montreal'] },
  { name: 'Seattle', iso2: 'US', lon: -122.33, lat: 47.61, kind: 'port', weight: 68, aliases: ['seattle', 'tacoma'] },
  { name: 'Oakland', iso2: 'US', lon: -122.27, lat: 37.80, kind: 'port', weight: 68, aliases: ['oakland'] },
  { name: 'Savannah', iso2: 'US', lon: -81.10, lat: 32.08, kind: 'port', weight: 66, aliases: ['savannah'] },
  { name: 'Charleston', iso2: 'US', lon: -79.93, lat: 32.78, kind: 'port', weight: 64, aliases: ['charleston'] },
  { name: 'New Orleans', iso2: 'US', lon: -90.07, lat: 29.95, kind: 'port', weight: 68, aliases: ['new orleans'] },
  { name: 'Corpus Christi', iso2: 'US', lon: -97.40, lat: 27.80, kind: 'port', weight: 68, aliases: ['corpus christi'] },
  { name: 'Veracruz', iso2: 'MX', lon: -96.13, lat: 19.17, kind: 'port', weight: 64, aliases: ['veracruz'] },
  { name: 'Manzanillo', iso2: 'MX', lon: -104.32, lat: 19.05, kind: 'port', weight: 64, aliases: ['manzanillo'] },
  { name: 'Callao', iso2: 'PE', lon: -77.15, lat: -12.06, kind: 'port', weight: 64, aliases: ['callao'] },
  { name: 'Valparaiso', iso2: 'CL', lon: -71.62, lat: -33.05, kind: 'port', weight: 62, aliases: ['valparaiso', 'valparaíso'] },
  { name: 'Buenaventura', iso2: 'CO', lon: -77.03, lat: 3.88, kind: 'port', weight: 60, aliases: ['buenaventura'] },
  { name: 'Cartagena', iso2: 'CO', lon: -75.51, lat: 10.39, kind: 'port', weight: 62, aliases: ['cartagena'] },
];

/** Index for fast lookup, built once. */
const BY_ALIAS = new Map<string, Place>();
for (const p of PLACES) {
  BY_ALIAS.set(p.name.toLowerCase(), p);
  for (const a of p.aliases ?? []) BY_ALIAS.set(a.toLowerCase(), p);
}

/**
 * Find the best place mentioned in `text`.
 *
 * Word-boundary matching (not raw substring) so "china" never matches "Chinatown"
 * and "Riyadh" is not found inside another word. Ties are broken by `weight`,
 * then by the LONGEST matched name (more specific wins: "Strait of Hormuz" over
 * "Hormuz").
 */
export function resolvePlace(text: string | null | undefined, countryHint?: string[]): Place | undefined {
  if (!text) return undefined;
  const hay = ` ${text.toLowerCase().replace(/[^a-z0-9\s'\-]/g, ' ').replace(/\s+/g, ' ')} `;
  let best: { place: Place; len: number } | null = null;
  for (const [alias, place] of BY_ALIAS) {
    if (!alias) continue;
    if (!hay.includes(` ${alias} `) && !hay.includes(` ${alias}'`) && !hay.includes(`-${alias} `)) {
      // Allow hyphenated forms like "bab-el-mandeb" and possessives.
      const escaped = alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (!new RegExp(`(^|[^a-z0-9])${escaped}([^a-z0-9]|$)`, 'i').test(hay)) continue;
    }
    // Prefer a place whose country the event already names — an event tagged
    // "Springfield" should resolve to the right country's place.
    const hinted = countryHint?.length ? countryHint.includes(place.iso2) : true;
    const score = (hinted ? 1000 : 0) + (place.weight ?? 50) + alias.length;
    if (!best || score > ((best.place.weight ?? 50) + best.len)) {
      best = { place, len: alias.length };
    }
  }
  return best?.place;
}

export function placeCount(): number {
  return PLACES.length;
}
