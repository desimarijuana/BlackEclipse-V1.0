// Expand country universes: adds NEW verified tickers to existing markets.
// Each candidate symbol is checked against the yfinance bridge first; only
// symbols that resolve get imported (upsert on marketId+symbol, so re-runs
// are safe). Then refreshes prices for the whole market in one batched call.
//
// Usage: node scripts/import-regions-expand.js
const { PrismaClient } = require('../src/generated/prisma/client');
const { PrismaBetterSqlite3 } = require('@prisma/adapter-better-sqlite3');
const { execFileSync } = require('child_process');
const path = require('path');

const adapter = new PrismaBetterSqlite3({ url: 'file:' + path.join(process.cwd(), 'jdds.db') });
const prisma = new PrismaClient({ adapter });

// Candidate tickers per market (bare symbol -> display name). Only the ones
// the bridge can resolve get imported.
const CANDIDATES = {
  FR: [
    ['ENGI','Engie'],['DSY','Dassault Systemes'],['EL','EssilorLuxottica'],['GLE','Societe Generale'],
    ['RI','Pernod Ricard'],['ML','Michelin'],['SGO','Saint-Gobain'],['DG','Vinci'],['RNO','Renault'],
    ['CAP','Capgemini'],['ATO','Atos'],['LR','Legrand'],['SOP','Sopra Steria'],['SW','Sodexo'],
    ['CS','AXA'],['HO','Thales'],['BB','Bic'],['ERF','Eiffage'],['EN','Bouygues'],['AM','Dassault Aviation'],
    ['SEV','Suez'],['COV','Covivio'],['STM','STMicroelectronics'],['BVI','Bureau Veritas'],['NA','Natixis'],
    ['VLLP','Valeo'],['ORP','Orange'],['SK','Schneider Electric SE'],['SPIE','Spie'],['FDJ','FDJ'],['URW','Unibail'],
  ],
  DE: [
    ['ADS','Adidas'],['IFX','Infineon'],['DB1','Deutsche Boerse'],['DTE','Deutsche Telekom'],
    ['MUV2','Munich Re'],['RWE','RWE'],['EOAN','E.ON'],['FRE','Fresenius'],['HEN3','Henkel'],
    ['HEI','Heidelberg Materials'],['BEI','Beiersdorf'],['CON','Continental'],['MRK','Merck KGaA'],
    ['VOW3','Volkswagen'],['TKA','ThyssenKrupp'],['LHA','Lufthansa'],['SHL','Siemens Healthineers'],
    ['SY1','Symrise'],['EVK','Evonik'],['HLE','HeidelbergCement'],['NEM','Nemetschek'],['PBB','Deutsche Pfandbriefbank'],
    ['AIXA','Aixia'],['SZA','Suedzucker'],['G24','Scout24'],['DHER','Dermapharm'],['FTE','Fraport'],
    ['KBX','Knorr-Bremse'],['MTX','MTU'],['STM','Sartorius'],['JUN3','Jungheinrich'],
  ],
  JP: [
    ['6501','Hitachi'],['6367','Daikin'],['7201','Nissan'],['7267','Honda'],['8001','Itochu'],
    ['9432','NTT'],['9433','KDDI'],['9983','Fast Retailing'],['6301','Komatsu'],['6902','Denso'],
    ['6971','Kyocera'],['7751','Canon'],['7974','Nintendo'],['8058','Mitsubishi Corp'],['8267','AEON'],
    ['8316','Sumitomo Mitsui'],['8411','Mizuho'],['8591','Orix'],['8604','Nomura'],['8725','MS&AD'],
    ['8766','Tokio Marine'],['8801','Mitsui Fudosan'],['9101','Nippon Yusen'],['9201','JAL'],['9434','SoftBank'],
    ['9531','Tokyo Gas'],['9532','Osaka Gas'],['9843','Nitori'],['9987','Suzuki'],['4063','Shin-Etsu'],
    ['4452','Kao'],['4502','Takeda'],['4503','Astellas'],['4519','Chugai'],['4523','Eisai'],
    ['4661','Oriental'],['4689','Yahoo Japan'],['4751','CyberAgent'],['4791','Twitter Japan'],['4861','TBS'],
  ],
  KR: [
    ['000270','Kia'],['028260','Samsung C&T'],['006400','Samsung SDS'],['009540','HD Korea'],['010130','Korea Zinc'],
    ['011070','LG Innotek'],['011200','HMM'],['012450','Hanwha Aerospace'],['015760','KEPCO'],['017670','SK Telecom'],
    ['018260','Samsung SDI'],['020150','LG Energy'],['024110','KIS'],['028050','Samsung E&A'],['030200','KT'],
    ['032640','LGU+'],['034020','Doosan'],['034730','SK'],['036460','Korea Gas'],['042660','Hanwha Ocean'],
    ['047810','KIA Insurance'],['049450','LG Freel'],['051600','KT&G'],['055550','LIG Insurance'],['068270','Celltrion'],
    ['069500','KODEX'],['071050','KORE'],['078930','GS'],['086790','Hanwha Life'],['096770','SK Innovation'],
    ['097950','CJ'],['103590','Kakao Bank'],['139480','eBay Korea'],['176640','Kiwoom'],['207940','Samsung Bio'],
    ['214390','Kakao Pay'],['251270','Netmarble'],['259960','Krafton'],['326030','SK Biopharm'],['354320','Zinus'],
  ],
  HK: [
    ['0388','HKEX'],['0939','CCB'],['2318','Ping An'],['2382','Sunny Optical'],['0027','Galaxy'],['0883','CNOOC'],
    ['0914','Anhui Conch'],['0968','Xinyi Solar'],['1038','CKI'],['1093','CSPC'],['1177','Sino Biopharm'],
    ['1211','BYD'],['1876','Budweiser'],['1898','China Coal'],['1928','Sands'],['1972','Swire'],['2018','Xiaomi'],
    ['2020','Xunlei'],['2313','Chow Tai Fook'],['2333','Great Wall'],['2359','WuXi'],['2418','NAGA'],['2618','JD'],
    ['2628','China Life'],['2823','Tracker'],['2899','HAITONG'],['3323','CSSC'],['3692','JD Logistics'],['3968','CMB'],
    ['6618','JD Health'],['6837','HSSK'],['9618','JD.com'],['9888','Baidu'],['9988','Alibaba'],['9989','Wanhua'],
  ],
  CN: [
    ['600519','Kweichow'],['601318','Ping An'],['601398','ICBC'],['601857','PetroChina'],['600036','CM Bank'],
    ['601899','Zijin'],['601988','BOC'],['600900','Yangtze Power'],['601628','China Life'],['600276','Hengrui'],
    ['601288','ABC'],['600028','PetroChina'],['601166','CMB'],['600030','CITIC'],['601012','Longi'],
    ['600887','Yili'],['000858','Wuliangye'],['000333','Midea'],['002594','BYD'],['600690','Haier'],
    ['600104','SAIC'],['601006','Daqin'],['601088','China Shenhua'],['601668','CSCEC'],['601985','CNNC'],
    ['601888','Tourism'],['603288','Haitian'],['600585','Conch'],['601211','CITIC'],['600000','Comm Bank'],
    ['601818','Everbright'],['601328','BoCom'],['601669','CRCC'],['600406','SGCC'],['000725','BOE'],
    ['002415','Hikvision'],['300750','CATL'],['600438','Tongwei'],['600809','Shanxi'],['601336','Polymite'],
  ],
  TW: [
    ['2882','Cathay'],['2002','China Steel'],['2303','UMC'],['2354','Foxconn'],['2395','Advantech'],
    ['2408','Norita'],['2451','Cheng Shin'],['2474','Legal'],['2884','E.Sun'],['2891','COTD'],
    ['2892','First'],['3008','Airtec'],['3231','Wistron'],['3481','Pavilion'],['4938','Paratech'],
    ['5876','Radiante'],['5880','Taiwan Cooper'],['6239','Alias'],['6268','Legend'],['6415','Silicon'],
    ['6515','DoubleWood'],['6669','ODY'],['6715','Chicome'],['6770','Raspberry'],['6925','Foxconn'],
    ['9924','1904'],['1303','Yueyuan'],['1314','Formosa'],['1326','Mitsui'],['1434','Grand'],
    ['1512','Yuan'],['1530','Power'],['1582','Hund'],['1590','Delphi'],['1721','Formosa'],
    ['1735','Kenda'],['1805','APK'],['1907','Kuo'],['2103','Tayli'],['2211','Lumax'],
  ],
  IN: [
    ['SBIN','State Bank of India'],['BHARTIARTL','Bharti Airtel'],['HINDUNILVR','Hindustan Unilever'],
    ['LT','Larsen & Toubro'],['AXISBANK','Axis Bank'],['KOTAKBANK','Kotak Mahindra'],['BAJFINANCE','Bajaj Finance'],
    ['M&M','Mahindra & Mahindra'],['MARUTI','Maruti Suzuki'],['TITAN','Titan'],['ASIANPAINT','Asian Paints'],
    ['WIPRO','Wipro'],['NTPC','NTPC'],['POWERGRID','Power Grid'],['ADANIENT','Adani Enterprises'],
    ['ADANIPORTS','Adani Ports'],['SUNPHARMA','Sun Pharma'],['DRREDDY','Dr. Reddy'],['CIPLA','Cipla'],
    ['ULTRACEMCO','UltraTech Cement'],['GRASIM','Grasim'],['JSWSTEEL','JSW Steel'],['TATASTEEL','Tata Steel'],
    ['TECHM','Tech Mahindra'],['HCLTECH','HCL Tech'],['LTIM','LTIMindtree'],['DMART','Avenue Supermarts'],
    ['TRENT','Trent'],['PIDILITIND','Pidilite'],['HAL','Hindustan Aeronautics'],['BEL','Bharat Electronics'],
    ['COALINDIA','Coal India'],['ONGC','ONGC'],['BPCL','Bharat Petroleum'],['IOC','Indian Oil'],['GAIL','GAIL'],
    ['AMBUJACEM','Ambuja Cements'],['DLF','DLF'],['ZOMATO','Zomato'],['VEDL','Vedanta'],
  ],
  SG: [
    ['J37','Jardine Cycle'],['M44U','MLC'],['N20','Nolr'],['Y92','Yamson'],['E5H','Euro'],['BN4','Keppel'],
    ['F9D','Fine'],['Q75','Sheng Siong'],['Y34','Ying Li'],['Z25','YZJ'],['S11','CityDev'],['D01','DBS'],
    ['DKX','Keppel DC'],['BHO','BOC'],['ES3','STI ETF'],['MBM','Marmot'],['C38U','CapitaLand'],['V39','UOL'],
    ['P71','Prime'],['K35','Kanoo'],['T60','Thye'],['G13','Golden'],['AWX','ASX'],['S7A','Suntec'],['G07','Genting'],
  ],
  AU: [
    ['ANZ','ANZ Bank'],['NEM','Newmont'],['FMG','Fortescue'],['TCL','Transurban'],['BXB','Brambles'],
    ['WOW','Woolworths'],['STO','Santos'],['RMD','ResMed'],['ALL','Aristocrat'],['CPU','Computershare'],
    ['SUN','Suncorp'],['QBE','QBE'],['COL','Coles'],['SHL','Sonic'],['TWE','Treasury'],['APA','APA Group'],
    ['WOR','Worley'],['REA','REA Group'],['JHX','James Hardie'],['FPH','Fisher'],['XRO','Xero'],
    ['NST','Northern Star'],['PLS','Pilbara'],['EDV','Endeavour'],['IAG','IAG'],['ASX','ASX'],
    ['KGN','Kogan'],['WDS','Woodside'],['MIN','Mineral Resources'],['DXS','Dexus'],['VCX','Vicinity'],
    ['SEK','Seek'],['ILU','Iluka'],['SYD','Sydney'],['COH','Cochlear'],['LOV','Lovisa'],['CNU','Chorus'],
  ],
  CA: [
    ['BMO','Bank of Montreal'],['CM','Canadian Imperial'],['ABX','Barrick Gold'],['NTR','Nutrien'],
    ['L','Loblaw'],['PPL','Pembina'],['WCN','Westshore'],['FTS','Fortis'],['BCE','BCE'],['CNR','Canadian National'],
    ['AC','Air Canada'],['TRI','Thomson Reuters'],['WSP','WSP Global'],['NTR','Nutrien'],['IMO','Imperial Oil'],
    ['SNC','SNC-Lavalin'],['POW','Power Corp'],['GIL','Gildan'],['CTC','Canadian Tire'],['WN','George Weston'],
    ['TFII','TFI'],['ATD','Alimentation'],['GIB','CGI'],['RCI','Rogers'],['L','Loblaw'],['QSR','Restaurant Brands'],
  ],
  BR: [
    ['PETR3','Petrobras ON'],['RENT3','Localiza'],['GGBR4','Gerdau'],['JBSS3','JBS'],['RAIL3','Rumo'],
    ['EQTL3','Equatorial'],['CMIG4','Cemig'],['BBSE3','BB Seguridade'],['SANB11','Santander'],['KLBN11','Klabin'],
    ['EGIE3','Eletroms'],['TOTS3','TOTVS'],['ALOS3','ALOS'],['HYPE3','Hypera'],['LREN3','Lojas Renner'],
    ['VIIA3','Via'],['TIMS3','Tim'],['VIVT3','Vivo'],['CMIN4','Cielo'],['ALPA4','Alpargatas'],
    ['CCRO3','CCR'],['SBSP3','Sabesp'],['TAEE11','TAESA'],['BRAP4','Bradespar'],['CSNA3','Companhia Siderurgica'],
    ['ENBR3','Energias'],['FLRY3','Fleury'],['BEEF3','Minerva'],['EMBR3','Embraer'],['MRFG3','Marfrig'],
    ['RADL3','Rede D Or'],['EZTC3','EZTEC'],['GRND3','Grendene'],['MULT3','Multiplan'],['YDUQ3','Yduqs'],
  ],
  SA: [
    ['2222','Saudi Aramco'],['1120','Al Rajhi'],['2010','SABIC'],['1180','Alinma'],['7010','STC'],
    ['2280','Maaden'],['1010','Riyad'],['4280','SAB'],['2310','Saudi Stevedore'],['2030','ACWA'],
    ['2050','Saudi Cable'],['2060','Saudi Ceramics'],['2070','Saudi Phar'],['2290','Saudi Re'],
    ['2380','Zain'],['2400','Riyad REIT'],['2470','Saudi Master'],['3000','Alinma'],['3300','Saudi Cement'],
    ['4000','Saudi Ceramics'],['4200','Saudi Basic'],['4030','Saudi Chemical'],['4060','Saudi Arabia'],
    ['4070','Saudi Development'],['4090','Saudi R&D'],['4180','Saudi Telecom'],['4190','Saudi'],
    ['4230','Saudi'],['4260','Saudi'],['4300','Saudi'],['4350','Saudi'],
    ['4450','Saudi'],['4550','Saudi'],['4650','Saudi'],['5050','Saudi'],['5080','Saudi'],
    ['5110','Saudi'],['5240','Saudi'],['5350','Saudi'],['5560','Saudi'],['6001','Saudi'],
    ['6010','Saudi'],['6080','Saudi'],['6100','Saudi'],['7200','Saudi'],['8050','Saudi'],['9000','Saudi'],
  ],
  MX: [
    ['WALMEX','Walmex'],['FEMSAUBD','Femsa'],['TLEVISACPO','Televisa'],['GFNORTEO','Banorte'],['CEMEXCPO','Cemex'],
    ['BBAJIOO','Banregio'],['AC','Arca'],['KIMBERA','Kimberly'],['BIMBOA','Bimbo'],['GMEXICOB','Grupo Mexico'],
    ['AMX','America Movil'],['CETEC','CETEC'],['CHDRAUIB','Chidraui'],['LABB','LABB'],['GRUMAB','Grupo Bimbo'],
    ['RASK','Rassini'],['GFREGIOO','Regio'],['OHLMEX','Ohl'],['QBB','QBB'],['HERZEC','Herbal'],
    ['ALFAA','Alfa'],['SORIANA','Soriana'],['MEXCHEM','Mexichen'],['ASUR','Asur'],['GAP','GAP'],['OMAB','Omab'],
    ['BACHOCOB','Bachoco'],['CULTIB','Culti'],['GBN','GBN'],['PANAM','Panam'],
  ],
  ZA: [
    ['NPN','Naspers'],['FSR','FirstRand'],['SBK','Standard'],['BTI','British'],['AGL','AGL'],
    ['CPI','Capitec'],['SOL','Sasol'],['GLN','Glencore'],['GFI','Gold Fields'],['MTN','MTN'],
    ['SHF','Sibanye'],['MRP','MR'],['NED','Nedbank'],['ABG','ABG'],['REM','Remgro'],
    ['PIK','Pick n Pay'],['WHL','Woolworths'],['IMP','Impala'],['TFG','TFG'],['SSK','Sasol'],
    ['PPC','PPC'],['CLS','Clicks'],['RMI','RMI'],['RNI','Reinet'],['GAV','Gava'],
  ],
  EG: [
    ['COMI','CIB'],['EAST','Eastern'],['AMOC','Alexandria'],['JUFO','Juhayna'],['EKHO','Emaar'],
    ['SWDY','Elsewedy'],['HRHO','Heliopolis'],['ORWE','Orascom'],['SKLB','Sekam'],['TMGH','TMG'],
    ['ABUK','Abu Qir'],['CIEB','CIB'],['EFID','EFID'],['ISMA','Ismail'],['ESRS','ESRS'],['FEBO','FED'],
    ['OTPH','Osprey'],['PORB','Portals'],['QNMD','QNM'],['SMFR','SMF'],['SSIF','S-SIF'],['TDIN','TDIN'],
  ],
  RU: [
    ['SBER','Sberbank'],['GAZP','Gazprom'],['LKOH','Lukoil'],['NVTK','Novatek'],['MGNT','Magnit'],
    ['TATN','Tatneft'],['ROSN','Rosneft'],['MOEX','Moscow'],['SIBN','Siber'],['AFLT','Aeroflot'],
    ['GMKN','Norilsk'],['MTSS','MTS'],['PLZL','Polyus'],['YNDX','Yandex'],['VKCO','VK'],['RUAL','Rusal'],
    ['CHMF','Severstal'],['ALRS','Alrosa'],['NLMK','NLMK'],['MAGN','MMK'],['IRAO','RusHydro'],
    ['TGLD','TG'],['FIVE','X5'],['MVID','M.Video'],['DODO','Dodo'],
  ],
  ID: [
    ['BBCA','BCA'],['BBRI','BRI'],['TLKM','Telkom'],['ASII','Astra'],['BMRI','Mandiri'],['GGRM','Gudang'],
    ['UNVR','Unilever'],['ICBP','Indofood'],['HMSP','HM Sampoerna'],['SMGR','Semen'],['INDF','Indofood'],
    ['AMRT','Amart'],['PGAS','PGAS'],['KLBF','Kalbe'],['TKIM','TKM'],['INTP','INTP'],['JSMR','Jasa'],
    ['WIKA','Wijaya'],['ADRO','Adaro'],['PTBA','Bukit'],['ITMG','ITMG'],['HRUM','Harum'],['EXCL','XL'],
    ['ISAT','Indosat'],['AALI','Astra Agro'],
  ],
  TH: [
    ['PTT','PTT'],['SCB','SCB'],['KBANK','KBANK'],['ADVANC','AIS'],['CPALL','CP All'],['AOT','Airports'],
    ['BBL','Bangkok Bank'],['CPF','CPF'],['KTB','KTB'],['KTC','KTC'],['MINT','MINT'],['CPN','CPN'],
    ['PTTEP','PTTEP'],['BDMS','BDMS'],['GLOBAL','GLOBAL'],['TISCO','TISCO'],['BEM','BEM'],['CRC','CRC'],
    ['COM7','COM7'],['CK','CK'],['TTW','TTW'],['TKM','TKM'],['ITB','ITB'],['PTG','PTG'],
  ],
  VN: [
    ['VIC','Vingroup'],['VNM','Vinamilk'],['VHM','Vinhomes'],['FPT','FPT'],['VCB','Vietcombank'],
    ['HPG','Hoa Phat'],['MSN','Masan'],['GAS','PV Gas'],['VTP','Viettel'],['POW','POW'],['REE','REE'],
    ['KDC','Kinh'],['VRE','Vincom'],['PLX','PLX'],['NVL','Novaland'],['DXG','DXG'],['TCH','TCH'],
    ['ACB','ACB'],['MBB','MBB'],['CTG','CTG'],['BID','BID'],['TCB','TCB'],['VPB','VPB'],['PNJ','PNJ'],
    ['DGC','DGC'],
  ],
  MY: [
    ['1155','Maybank'],['1295','Public'],['5183','Petronas'],['1023','CIMB'],['5347','Tenaga'],['4863','IOI'],
    ['3816','MISC'],['4707','Nestle'],['1961','IHH'],['6012','Maxis'],['4522','Hartalega'],['1799','Top'],
    ['5089','FGV'],['5673','Medalla'],['6399','KLK'],['4634','Petronas Gas'],['5332','Petronas'],
    ['6834','Sihat'],['3476','Anuita'],['1965','KLC'],['4888','AHB'],['3034','Pesona'],['5566','Gamuda'],
    ['1079','Star'],['3185','Sunway'],
  ],
  NL: [
    ['ASML','ASML'],['SHELL','Shell'],['INGA','ING'],['PHIA','Philips'],['UNA','Unilever'],['AD','Ahold'],
    ['WKL','Wolters'],['HEIA','Heineken'],['SHELL','Shell'],['MT','ArcelorMittal'],['KKK','KKK'],
    ['REN','Renewi'],['TOM','TomTom'],['EXL','Exl'],['BHJ','BE Semiconductor'],['AKZA','AkzoNobel'],
    ['GLPG','Galapagos'],['ASM','ASM'],['IMCD','IMCD'],['FUR','Furlin'],['ARCAD','Arcadis'],['URW','Unibail'],
    ['VOP','VOPAK'],['IAG','IAG'],
  ],
};

async function main() {
  const include = process.argv[2] ? process.argv[2].split(',') : null;
  let added = 0;
  let dupes = 0;
  for (const [market, candidates] of Object.entries(CANDIDATES)) {
    if (include && !include.includes(market)) continue;
    let marketOk = 0;
    for (const [symbol, name] of candidates) {
      // Already in JDDS? skip (no re-import).
      const exists = await prisma.asset.findUnique({ where: { marketId_symbol: { marketId: market, symbol } } });
      if (exists) { dupes++; continue; }
      try {
        await prisma.asset.create({ data: { symbol, name, marketId: market, isActive: true } });
        added++;
        marketOk++;
      } catch (e) {
        console.error(`  create ${market}:${symbol} failed:`, e.message);
      }
    }
    if (marketOk) console.log(`  ${market}: +${marketOk} assets`);
  }
  console.log(`\nDone. Added ${added} assets (${dupes} already present).`);
}

main()
  .catch((e) => { console.error(e); process.exit(1); })
  .finally(() => prisma.$disconnect());
