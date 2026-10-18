# Stage 1 company finder

Built 2026-10-18T18:59:39Z. 3,906 news items from 119 publishers/feeds, scored with FinBERT and linked to companies and industries.

Rules: **A** market sentiment, **B** competition & news releases (rivals' news flipped), **C** manufacturing industry (supply chain), **D** customers. Each −1…+1. News composite weights A 30%, B 25%, C 20%, D 25%. Lead score = ½ news composite + ½ quant-model signal (the Milestone 2 model chosen for the company: expected 1-year excess return over its spread).

## Top 50 listed leads

| # | Company | Exchange | Score | News | Model | A | B | C | D | Items | Model (1y expected) | Best route for an Indian resident |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | COSCO SHIPPING Holdings Co., Ltd. (601919.SS) | SSE | **+0.55** | +0.79 | +0.31 | +0.79 | -0.93 | — | — | 3 | EWMA vol + shrunk drift (+9%) | H-shares on HKEX under LRS (1919.HK) |
| 2 | Eli Lilly and Company (LLY) | NYSE | **+0.53** | +0.23 | +0.84 | +0.03 | -0.01 | +0.89 | +0.71 | 87 | GJR-GARCH(1,1)-t (+46%) | US-listed shares under LRS (LLY) |
| 3 | The Magnum Ice Cream Company N.V. (MICC.AS) | EURONEXT_AS | **+0.53** | +0.53 | — | — | +0.84 | — | +0.23 | 6 | — (—) | ADR under LRS (MICC) |
| 4 | Orient Overseas (International) Limited (0316.HK) | HKEX | **+0.52** | +0.93 | +0.11 | +0.93 | -0.07 | — | — | 3 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (0316.HK) |
| 5 | Bank of Communications Co., Ltd. (601328.SS) | SSE | **+0.46** | +0.39 | +0.53 | +0.71 | +0.09 | +0.30 | +0.87 | 56 | EWMA vol + shrunk drift (+12%) | H-shares on HKEX under LRS (3328.HK) |
| 6 | Uni-President Enterprises Corp. (1216.TW) | TWSE | **+0.44** | +0.53 | +0.34 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+8%) | Country ETF under LRS (EWT) |
| 7 | Inner Mongolia Yili Industrial Group Co., Ltd. (600887.SS) | SSE | **+0.43** | +0.48 | +0.39 | — | +0.73 | — | +0.23 | 9 | EWMA vol + shrunk drift (+7%) | A-shares via Northbound Stock Connect (600887.SS) |
| 8 | Manulife Financial Corporation (MFC.TO) | TSX | **+0.40** | +0.36 | +0.44 | +0.47 | +0.28 | +0.30 | +0.56 | 13 | EWMA vol + shrunk drift (+10%) | US-listed ordinary shares under LRS (MFC) |
| 9 | Tata Consumer Products Limited (TATACONSUM.NS) | NSE | **+0.40** | +0.53 | +0.26 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+11%) | Buy directly on NSE/BSE (TATACONSUM.NS) |
| 10 | Orkla ASA (ORK.OL) | EURONEXT_OL | **+0.38** | +0.52 | +0.24 | +0.01 | +0.81 | — | +0.23 | 7 | EWMA vol + shrunk drift (+9%) | Home-market shares under LRS (ORK.OL) |
| 11 | Lotus Bakeries NV (LOTB.BR) | EURONEXT_BR | **+0.38** | +0.53 | +0.22 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (LOTB.BR) |
| 12 | Royal Bank of Canada (RY.TO) | TSX | **+0.38** | +0.25 | +0.51 | +0.33 | +0.10 | +0.30 | +0.87 | 75 | EWMA vol + shrunk drift (+11%) | US-listed ordinary shares under LRS (RY) |
| 13 | Coal India Limited (COALINDIA.NS) | NSE | **+0.38** | +0.31 | +0.44 | +0.54 | +0.30 | -0.91 | +0.32 | 5 | EWMA vol + shrunk drift (+15%) | Buy directly on NSE/BSE (COALINDIA.NS) |
| 14 | Industrial and Commercial Bank of China Limited (601398.SS) | SSE | **+0.37** | +0.18 | +0.55 | +0.88 | +0.09 | +0.30 | +0.87 | 54 | EWMA vol + shrunk drift (+12%) | H-shares on HKEX under LRS (1398.HK) |
| 15 | PetroChina Company Limited (601857.SS) | SSE | **+0.36** | +0.40 | +0.32 | +0.76 | -0.18 | — | +0.54 | 68 | EWMA vol + shrunk drift (+10%) | H-shares on HKEX under LRS (0857.HK) |
| 16 | Almarai Company (2280.SR) | TADAWUL | **+0.35** | +0.53 | +0.18 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+8%) | Country ETF under LRS (KSA) |
| 17 | China Construction Bank Corporation (601939.SS) | SSE | **+0.35** | +0.18 | +0.51 | +0.11 | +0.09 | +0.30 | +0.87 | 54 | EWMA vol + shrunk drift (+12%) | H-shares on HKEX under LRS (0939.HK) |
| 18 | InterContinental Hotels Group PLC (IHG.L) | LSE | **+0.35** | +0.44 | +0.25 | +0.39 | +0.18 | — | +0.76 | 24 | EWMA vol + shrunk drift (+10%) | ADR under LRS (IHG) |
| 19 | China Shenhua Energy Company Limited (601088.SS) | SSE | **+0.35** | +0.26 | +0.43 | — | +0.20 | -0.91 | +0.32 | 5 | EWMA vol + shrunk drift (+11%) | H-shares on HKEX under LRS (1088.HK) |
| 20 | Tingyi (Cayman Islands) Holding Corp. (0322.HK) | HKEX | **+0.34** | +0.53 | +0.15 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (0322.HK) |
| 21 | The Indian Hotels Company Limited (INDHOTEL.NS) | NSE | **+0.34** | +0.33 | +0.35 | — | -0.10 | — | +0.76 | 24 | EWMA vol + shrunk drift (+15%) | Buy directly on NSE/BSE (INDHOTEL.NS) |
| 22 | Agricultural Bank of China Limited (601288.SS) | SSE | **+0.34** | +0.15 | +0.53 | +0.09 | +0.09 | +0.30 | +0.87 | 54 | EWMA vol + shrunk drift (+13%) | H-shares on HKEX under LRS (1288.HK) |
| 23 | Foshan Haitian Flavouring and Food Company Ltd. (603288.SS) | SSE | **+0.34** | +0.48 | +0.19 | — | +0.73 | — | +0.23 | 9 | EWMA vol + shrunk drift (+5%) | H-shares on HKEX under LRS (3288.HK) |
| 24 | WH Group Limited (0288.HK) | HKEX | **+0.34** | +0.53 | +0.14 | — | +0.84 | — | +0.23 | 6 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (0288.HK) |
| 25 | Bank of China Limited (601988.SS) | SSE | **+0.33** | +0.18 | +0.48 | — | +0.09 | +0.30 | +0.87 | 54 | EWMA vol + shrunk drift (+13%) | H-shares on HKEX under LRS (3988.HK) |
| 26 | Welltower Inc. (WELL) | NYSE | **+0.33** | +0.27 | +0.39 | +0.38 | +0.30 | +0.08 | — | 11 | EWMA vol + shrunk drift (+11%) | US-listed shares under LRS (WELL) |
| 27 | Glanbia plc (GL9.IR) | EURONEXT_IR | **+0.32** | +0.53 | +0.11 | +0.05 | +0.84 | — | +0.23 | 7 | EWMA vol + shrunk drift (+6%) | Home-market shares under LRS (GL9.IR) |
| 28 | Ajinomoto Co., Inc. (2802.T) | JPX | **+0.32** | +0.45 | +0.20 | -0.91 | +0.66 | — | +0.23 | 9 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (2802.T) |
| 29 | Titan Company Limited (TITAN.NS) | NSE | **+0.32** | +0.29 | +0.35 | — | -0.18 | — | +0.76 | 23 | EWMA vol + shrunk drift (+14%) | Buy directly on NSE/BSE (TITAN.NS) |
| 30 | Taiwan Mobile Co., Ltd. (3045.TW) | TWSE | **+0.32** | +0.33 | +0.30 | +0.72 | +0.33 | +0.68 | +0.09 | 9 | EWMA vol + shrunk drift (+8%) | Country ETF under LRS (EWT) |
| 31 | Midea Group Co., Ltd. (000333.SZ) | SZSE | **+0.32** | +0.29 | +0.34 | +0.35 | +0.23 | +0.68 | +0.09 | 11 | EWMA vol + shrunk drift (+9%) | H-shares on HKEX under LRS (0300.HK) |
| 32 | Bharat Electronics Limited (BEL.NS) | NSE | **+0.32** | +0.19 | +0.44 | — | -0.04 | +0.47 | — | 98 | EWMA vol + shrunk drift (+16%) | Buy directly on NSE/BSE (BEL.NS) |
| 33 | Associated British Foods plc (ABF.L) | LSE | **+0.31** | +0.49 | +0.14 | +0.06 | +0.75 | — | +0.23 | 9 | EWMA vol + shrunk drift (+7%) | Home-market shares under LRS (ABF.L) |
| 34 | Sun Pharmaceutical Industries Limited (SUNPHARMA.NS) | NSE | **+0.31** | +0.16 | +0.47 | — | -0.04 | — | +0.36 | 20 | EWMA vol + shrunk drift (+14%) | Buy directly on NSE/BSE (SUNPHARMA.NS) |
| 35 | Oil and Natural Gas Corporation Limited (ONGC.NS) | NSE | **+0.31** | +0.17 | +0.45 | — | -0.20 | — | +0.54 | 62 | EWMA vol + shrunk drift (+14%) | Buy directly on NSE/BSE (ONGC.NS) |
| 36 | Torrent Pharmaceuticals Limited (TORNTPHARM.NS) | NSE | **+0.31** | +0.16 | +0.46 | — | -0.04 | — | +0.36 | 20 | EWMA vol + shrunk drift (+15%) | Buy directly on NSE/BSE (TORNTPHARM.NS) |
| 37 | Yankuang Energy Group Company Limited (600188.SS) | SSE | **+0.31** | +0.46 | +0.16 | +0.44 | +0.62 | -0.91 | +0.32 | 5 | EWMA vol + shrunk drift (+8%) | H-shares on HKEX under LRS (1171.HK) |
| 38 | DENSO Corporation (6902.T) | JPX | **+0.31** | +0.43 | +0.18 | +0.59 | -0.73 | — | +0.25 | 4 | EWMA vol + shrunk drift (+5%) | Home-market shares under LRS (6902.T) |
| 39 | S.F. Holding Co., Ltd. (002352.SZ) | SZSE | **+0.30** | +0.31 | +0.29 | — | +0.30 | +0.33 | — | 4 | EWMA vol + shrunk drift (+6%) | A-shares via Northbound Stock Connect (002352.SZ) |
| 40 | Sun Life Financial Inc. (SLF.TO) | TSX | **+0.30** | +0.17 | +0.44 | +0.28 | +0.01 | +0.08 | +0.24 | 30 | EWMA vol + shrunk drift (+9%) | US-listed ordinary shares under LRS (SLF) |
| 41 | ExxonMobil Holdings Corporation (XOM) | NYSE | **+0.30** | +0.32 | +0.28 | +0.42 | -0.03 | — | +0.54 | 68 | EWMA vol + shrunk drift (+11%) | US-listed shares under LRS (XOM) |
| 42 | The Travelers Companies, Inc. (TRV) | NYSE | **+0.30** | +0.25 | +0.35 | +0.39 | +0.09 | -0.91 | +0.24 | 36 | EWMA vol + shrunk drift (+11%) | US-listed shares under LRS (TRV) |
| 43 | GE Aerospace (GE) | NYSE | **+0.30** | +0.28 | +0.32 | +0.36 | +0.02 | +0.47 | — | 98 | EWMA vol + shrunk drift (+11%) | US-listed shares under LRS (GE) |
| 44 | Poste Italiane S.p.A. (PST.MI) | EURONEXT_MI | **+0.30** | +0.31 | +0.29 | — | +0.30 | +0.33 | — | 4 | EWMA vol + shrunk drift (+9%) | Home-market shares under LRS (PST.MI) |
| 45 | International Consolidated Airlines Group S.A. (1IAG.MI) | EURONEXT_MI | **+0.30** | +0.27 | +0.33 | +0.18 | +0.19 | -0.20 | +0.81 | 26 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (1IAG.MI) |
| 46 | InterGlobe Aviation Limited (INDIGO.NS) | NSE | **+0.29** | +0.29 | +0.30 | — | +0.15 | -0.20 | +0.81 | 26 | EWMA vol + shrunk drift (+13%) | Buy directly on NSE/BSE (INDIGO.NS) |
| 47 | Orange S.A. (ORA.PA) | EURONEXT_PA | **+0.29** | +0.36 | +0.23 | +0.63 | +0.03 | — | — | 44 | EWMA vol + shrunk drift (+8%) | Home-market shares under LRS (ORA.PA) |
| 48 | British American Tobacco p.l.c. (BATS.L) | LSE | **+0.29** | +0.39 | +0.19 | +0.59 | +0.15 | — | — | 34 | EWMA vol + shrunk drift (+8%) | ADR under LRS (BTI) |
| 49 | Gilead Sciences, Inc. (GILD) | NASDAQ | **+0.29** | +0.35 | +0.23 | +0.35 | -0.02 | +0.89 | +0.71 | 90 | EWMA vol + shrunk drift (+10%) | US-listed shares under LRS (GILD) |
| 50 | Makkah Construction and Development Company (4100.SR) | TADAWUL | **+0.29** | +0.33 | +0.24 | — | -0.10 | — | +0.76 | 24 | EWMA vol + shrunk drift (+10%) | Country ETF under LRS (KSA) |

## Weakest 10 listed (most negative)

| Company | Score | News | Model | Verdict |
|---|---|---|---|---|
| Wan Hai Lines Ltd. (2615.TW) | -0.38 | -0.86 | +0.10 | Bearish |
| HMM Co.,Ltd (011200.KS) | -0.36 | -0.86 | +0.14 | Bearish |
| Evergreen Marine Corporation (Taiwan) Ltd. (2603.TW) | -0.36 | -0.86 | +0.15 | Bearish |
| Adani Ports and Special Economic Zone Limited (ADANIPORTS.NS) | -0.31 | -0.86 | +0.24 | Bearish |
| Moncler S.p.A. (MONC.MI) | -0.27 | -0.66 | +0.11 | Bearish |
| The National Shipping Company of Saudi Arabia (4030.SR) | -0.23 | -0.86 | +0.40 | Bearish |
| Aker BP ASA (AKRBP.OL) | -0.20 | -0.57 | +0.17 | Bearish |
| Convatec Group PLC (CTEC.L) | -0.15 | -0.42 | +0.12 | Bearish |
| Metlen Energy & Metals PLC (MTLN.L) | -0.15 | -0.40 | +0.10 | Bearish |
| BE Semiconductor Industries N.V. (BESI.AS) | -0.14 | -0.34 | +0.05 | Bearish |

## Evidence for the top 5

**COSCO SHIPPING Holdings Co., Ltd.** — peers used for rule B: Adani Ports and Special Economic Zone Limited, Evergreen Marine Corporation (Taiwan) Ltd., HMM Co.,Ltd, Orient Overseas (International) Limited, Wan Hai Lines Ltd., The National Shipping Company of Saudi Arabia

- A: OOCL revenue up 45.1% on trans-Pacific surge (FreightWaves, 2026-10-12, FinBERT +0.93)
- A: 4 Ways to Play the Shipping Industry in the Face of the Gas Crunch (MarketBeat, 2026-10-05, FinBERT +0.07)
- A: COSCO SHIPPING Holdings Co Ltd's Dividend Analysis (GuruFocus.com, 2026-09-23, FinBERT +0.01)

**Eli Lilly and Company** — peers used for rule B: Johnson & Johnson, AbbVie Inc., Merck & Co., Inc., Novartis AG, AstraZeneca PLC, Amgen Inc.

- A: Novo Nordisk’s Growth Story Is Under Pressure as Eli Lilly Gains Ground (Insider Monkey, 2026-10-16, FinBERT -0.92)
- A: Is Novo Nordisk (CPSE:NOVO B) Facing A Bigger Threat In Europe? (Simply Wall St., 2026-10-18, FinBERT -0.56)
- A: Lilly’s Foundayo wins EMA panel backing for obesity and type 2 diabetes (Pharmaceutical Technology, 2026-10-16, FinBERT +0.89)
- C: UCB announces U.S. FDA approval for ZILBRYSQ® (zilucoplan) autoinjector self-administration for adults living with generalized myasthenia gravis (PR Newswire, 2026-10-16, FinBERT +0.89)
- D: HeartBeam Joins European EXIT-CVD Research Consortium to Advance At-Home ECG Monitoring for Early Detection of Acute Coronary Syndrome (ACS) in High-Risk Patients (Business Wire, 2026-10-15, FinBERT +0.70)
- D: Takeda’s ORZEYFUL (oveporexton) Launches Simultaneously in Japan and China Giving Physicians First Access to Prescribe Novel Orexin Agonist to Patients with Narcolepsy Type 1 (Business Wire, 2026-10-15, FinBERT +0.72)

**The Magnum Ice Cream Company N.V.** — peers used for rule B: Danone S.A., Ajinomoto Co., Inc., Foshan Haitian Flavouring and Food Company Ltd., Inner Mongolia Yili Industrial Group Co., Ltd., Nestlé India Limited, Associated British Foods plc

- A: Director/PDMR Shareholding (GlobeNewswire, 2026-09-22, FinBERT +0.01)
- D: Will Caterpillar's Strong Volume Growth Keep Driving Sales Up in 2026? (Zacks, 2026-10-09, FinBERT +0.92)
- D: 3 Stocks to Watch as Wall Street Wealth Fuels Consumer Spending (MarketBeat, 2026-10-16, FinBERT +0.09)
- D: ZTO Express (ZTO) Stock May Be Undervalued On Fresh Parcel Volume Growth (Simply Wall St., 2026-09-24, FinBERT -0.57)

**Orient Overseas (International) Limited** — peers used for rule B: Adani Ports and Special Economic Zone Limited, COSCO SHIPPING Holdings Co., Ltd., Evergreen Marine Corporation (Taiwan) Ltd., HMM Co.,Ltd, Wan Hai Lines Ltd., The National Shipping Company of Saudi Arabia

- A: Orient Overseas International (SEHK:316) Faces A 38% Premium Following Strong Q3 Operating Growth (Simply Wall St., 2026-10-13, FinBERT +0.93)
- A: OOCL revenue up 45.1% on trans-Pacific surge (FreightWaves, 2026-10-12, FinBERT +0.93)
- A: Orient Overseas (International) (SEHK:316) Stock Looks Overvalued On Dividend Value (Simply Wall St., 2026-09-21, FinBERT -0.43)

**Bank of Communications Co., Ltd.** — peers used for rule B: JPMorgan Chase & Co., Industrial and Commercial Bank of China Limited, Agricultural Bank of China Limited, Bank of America Corporation, China Construction Bank Corporation, HSBC Holdings plc

- A: Bank Of Communications (SEHK:3328) Stock Looks Undervalued After Its 154% Run (Simply Wall St., 2026-10-09, FinBERT +0.76)
- A: Is Bank Of Communications (SEHK:3328) Fairly Valued After Its Tier 2 Bond Redemption? (Simply Wall St., 2026-10-08, FinBERT +0.66)
- C: Crédit Agricole Stock And Eurozone Cash Plays for Higher Bond Yields (Simply Wall St., 2026-10-15, FinBERT +0.80)
- C: Global Bond Yields Edge Higher on Slowing Bond Selloff (The Wall Street Journal, 2026-10-09, FinBERT +0.82)
- C: European bank shares fall as bond yields surge, spreads widen (Reuters, 2026-10-07, FinBERT -0.95)
- D: ICICI Bank Q2 profit beats estimates on strong loan growth (Investing.com, 2026-10-17, FinBERT +0.87)
- D: Can U.K. Loan Growth & Tech Spending Lift Barclays' Earnings? (Zacks, 2026-09-24, FinBERT +0.90)

## New listings (first year of trading)

None found in the current news window.

## IPO pipeline (not trading yet)

| Company | Stage | Country | Score | Stories | Route | Latest headline |
|---|---|---|---|---|---|---|
| National Stock Exchange of India | priced | IN | +0.01 | 1 | Apply in the IPO | National Stock Exchange of India Sets Price Band for IPO |

## Markets to consider adding (news on growing industries)

| Market | Exchange | Stories | Growth stories | Sentiment | Sectors | Suggest |
|---|---|---|---|---|---|---|
| AU | ASX | 9 | 0 | +0.09 | Energy, Materials & Utilities / Healthcare & Biotech | no |
| AE | ADX | 7 | 2 | +0.36 | — | no |
| DE | XETRA | 5 | 0 | +0.32 | — | no |
| BR | B3 | 4 | 0 | -0.38 | Energy, Materials & Utilities | no |
| MX | BMV | 4 | 0 | -0.01 | — | no |
| DK | OMX_CPH | 4 | 1 | +0.38 | — | no |
| SG | SGX | 2 | 0 | +0.32 | — | no |
| ID | IDX | 2 | 0 | +0.42 | — | no |
| MY | BURSA | 2 | 2 | +0.00 | — | no |
| TR | BIST | 2 | 0 | +0.84 | — | no |
| ZA | JSE | 1 | 1 | -0.46 | — | no |
| EG | EGX | 1 | 0 | +0.88 | — | no |
| NG | NGX | 1 | 0 | +0.15 | — | no |
| ES | BME | 1 | 0 | +0.93 | — | no |
| SE | OMX_STO | 1 | 0 | -0.89 | — | no |
| PL | GPW | 1 | 0 | +0.08 | — | no |

Routes follow Indian-resident rules as of the dates in config/routes.yaml; check them before acting. Research output, not investment advice.
