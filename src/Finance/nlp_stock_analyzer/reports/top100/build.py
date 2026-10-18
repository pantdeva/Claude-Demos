import json, re
raw = """1|NVIDIA|NVDA|5170|USA
2|Apple|AAPL|5012|USA
3|Alphabet (Google)|GOOGL|4120|USA
4|Microsoft|MSFT|3928|USA
5|Amazon|AMZN|2696|USA
6|TSMC|2330.TW|2139|Taiwan
7|SpaceX|SPCX|1923|USA
8|Meta Platforms|META|1807|USA
9|Saudi Aramco|2222.SR|1629|Saudi Arabia
10|Broadcom|AVGO|1569|USA
11|Tesla|TSLA|1400|USA
12|Berkshire Hathaway|BRK-B|1138|USA
13|Eli Lilly|LLY|1120|USA
14|Samsung Electronics|005930.KS|1051|South Korea
15|Micron Technology|MU|994.34|USA
16|Walmart|WMT|942.60|USA
17|JPMorgan Chase|JPM|902.16|USA
18|AMD|AMD|863.17|USA
19|Visa|V|755.84|USA
20|Exxon Mobil|XOM|735.95|USA
21|SK Hynix|000660.KS|694.66|South Korea
22|ASML|ASML|630.50|Netherlands
23|Johnson & Johnson|JNJ|615.87|USA
24|Mastercard|MA|540.86|USA
25|AbbVie|ABBV|504.37|USA
26|CXMT|688825.SS|477.54|China
27|Tencent|0700.HK|476.49|China
28|Intel|INTC|474.95|USA
29|China Construction Bank|0939.HK|448.67|China
30|Palantir|PLTR|447.04|USA
31|Chevron|CVX|441.34|USA
32|Costco|COST|438.30|USA
33|Cisco|CSCO|423.39|USA
34|Coca-Cola|KO|404.00|USA
35|Oracle|ORCL|388.72|USA
36|Agricultural Bank of China|601288.SS|379.55|China
37|Roche|ROG.SW|371.73|Switzerland
38|Procter & Gamble|PG|370.39|USA
39|UnitedHealth|UNH|360.32|USA
40|Merck & Co.|MRK|360.08|USA
41|Bank of America|BAC|358.23|USA
42|ICBC|1398.HK|344.69|China
43|Caterpillar|CAT|335.91|USA
44|Bank of China|3988.HK|333.98|China
45|Lam Research|LRCX|330.30|USA
46|General Electric|GE|325.61|USA
47|Applied Materials|AMAT|324.81|USA
48|HSBC|HSBA.L|323.42|UK
49|Philip Morris International|PM|319.82|USA
50|Home Depot|HD|308.91|USA
51|Shell|SHEL.L|303.38|UK
52|Netflix|NFLX|293.68|USA
53|Dell Technologies|DELL|287.20|USA
54|Novartis|NOVN.SW|286.28|Switzerland
55|Morgan Stanley|MS|283.59|USA
56|Palo Alto Networks|PANW|279.75|USA
57|Royal Bank of Canada|RY.TO|273.84|Canada
58|Alibaba|9988.HK|271.43|China
59|RTX|RTX|261.35|USA
60|SAP|SAP.DE|258.87|Germany
61|Nestlé|NESN.SW|257.21|Switzerland
62|Goldman Sachs|GS|256.59|USA
63|AstraZeneca|AZN.L|256.53|UK
64|Thermo Fisher Scientific|TMO|255.12|USA
65|Texas Instruments|TXN|252.49|USA
66|Wells Fargo|WFC|251.74|USA
67|Kweichow Moutai|600519.SS|248.85|China
68|Mitsubishi UFJ Financial|8306.T|246.27|Japan
69|GE Vernova|GEV|245.34|USA
70|L'Oréal|OR.PA|243.62|France
71|Arm Holdings|ARM|243.29|UK
72|Amgen|AMGN|233.81|USA
73|PetroChina|0857.HK|233.09|China
74|CrowdStrike|CRWD|232.83|USA
75|Siemens|SIE.DE|232.69|Germany
76|Linde|LIN|229.76|UK
77|Toyota|7203.T|229.21|Japan
78|China Mobile|0941.HK|223.66|China
79|Arista Networks|ANET|223.21|USA
80|LVMH|MC.PA|219.82|France
81|IBM|IBM|218.70|USA
82|Shopify|SHOP|218.11|Canada
83|KLA|KLAC|216.29|USA
84|American Express|AXP|211.77|USA
85|BHP Group|BHP.AX|211.67|Australia
86|International Holding Company|IHC.AE|210.60|UAE
87|MediaTek|2454.TW|209.38|Taiwan
88|Citigroup|C|208.43|USA
89|Marvell Technology|MRVL|204.75|USA
90|TotalEnergies|TTE.PA|201.38|France
91|Salesforce|CRM|198.09|USA
92|Toronto-Dominion Bank|TD.TO|196.59|Canada
93|Amphenol|APH|195.67|USA
94|Inditex|ITX.MC|195.44|Spain
95|Gilead Sciences|GILD|193.66|USA
96|Banco Santander|SAN.MC|192.28|Spain
97|CATL|300750.SZ|191.99|China
98|Analog Devices|ADI|191.61|USA
99|Walt Disney|DIS|190.95|USA
100|Sandisk|SNDK|187.78|USA"""
rows=[]
for line in raw.splitlines():
    r,n,t,mc,c=line.split("|"); rows.append({"rank":int(r),"name":n,"ticker":t,"mcap_b":float(mc),"country":c})
for i in range(1,len(rows)): assert rows[i]["mcap_b"]<=rows[i-1]["mcap_b"], rows[i]
assert len(rows)==100 and [r["rank"] for r in rows]==list(range(1,101))

DOW={"AAPL","MSFT","NVDA","GOOGL","AMZN","WMT","JPM","V","JNJ","KO","PG","MRK","UNH","CSCO","CAT","HD","GS","AXP","IBM","CVX","AMGN","DIS","CRM"}
NDX={"NVDA","AAPL","MSFT","AMZN","GOOGL","SPCX","META","AVGO","TSLA","MU","WMT","AMD","ASML","INTC","PLTR","COST","CSCO","LRCX","AMAT","NFLX","PANW","TXN","ARM","AMGN","CRWD","LIN","SHOP","KLAC","MRVL","GILD","ADI","SNDK"}
NOT_SPX={"SPCX","ARM","SHOP","ASML"}  # non-US or not yet eligible
OTHER={
 "2330.TW":["TAIEX"],"2454.TW":["TAIEX"],"2222.SR":["Tadawul (TASI)"],
 "005930.KS":["KOSPI"],"000660.KS":["KOSPI"],
 "ASML":["Euro Stoxx 50","AEX"],"SAP.DE":["Euro Stoxx 50","DAX"],"SIE.DE":["Euro Stoxx 50","DAX"],
 "OR.PA":["Euro Stoxx 50","CAC 40"],"MC.PA":["Euro Stoxx 50","CAC 40"],"TTE.PA":["Euro Stoxx 50","CAC 40"],
 "ITX.MC":["Euro Stoxx 50","IBEX 35"],"SAN.MC":["Euro Stoxx 50","IBEX 35"],
 "ROG.SW":["SMI"],"NOVN.SW":["SMI"],"NESN.SW":["SMI"],
 "HSBA.L":["FTSE 100","Hang Seng"],"SHEL.L":["FTSE 100"],"AZN.L":["FTSE 100"],
 "0700.HK":["Hang Seng"],"9988.HK":["Hang Seng"],
 "0939.HK":["Hang Seng","CSI 300"],"1398.HK":["Hang Seng","CSI 300"],"3988.HK":["Hang Seng","CSI 300"],
 "0857.HK":["Hang Seng","CSI 300"],"0941.HK":["Hang Seng","CSI 300"],
 "601288.SS":["CSI 300"],"600519.SS":["CSI 300"],"300750.SZ":["CSI 300"],
 "688825.SS":["MSCI China (not yet CSI 300)"],
 "8306.T":["Nikkei 225"],"7203.T":["Nikkei 225"],
 "RY.TO":["S&P/TSX 60"],"TD.TO":["S&P/TSX 60"],"SHOP":["S&P/TSX 60"],
 "BHP.AX":["S&P/ASX 200"],"IHC.AE":["FTSE ADX General"],
}
for r in rows:
    t=r["ticker"]; idx=[]
    us = r["country"]=="USA" or t in {"LIN"}
    if us and t not in NOT_SPX: idx.append("S&P 500")
    if t in NDX: idx.append("Nasdaq-100")
    if t in DOW: idx.append("Dow 30")
    idx += OTHER.get(t,[])
    assert idx, t
    r["indexes"]=idx
notes={"SPCX":"Listed June 2026; joined Nasdaq-100 on 7 Jul 2026; S&P 500 not before mid-2027",
       "688825.SS":"Listed on Shanghai's STAR Market July 2026; added to MSCI China in August",
       "GOOGL":"Joined the Dow on 29 Jun 2026","MRVL":"Joined the S&P 500 on 22 Jun 2026",
       "WMT":"Moved to Nasdaq; joined the Nasdaq-100 in Jan 2026","SNDK":"Joined the Nasdaq-100 on 20 Apr 2026",
       "AZN.L":"Left the Nasdaq-100 in Jan 2026","LIN":"Listed in New York; incorporated in Ireland, HQ in UK"}
for r in rows:
    if r["ticker"] in notes: r["note"]=notes[r["ticker"]]
json.dump(rows, open("top100.json","w"), indent=1)
from collections import Counter
tot=sum(r["mcap_b"] for r in rows)
c=Counter(); 
for r in rows: c[r["country"]]+=r["mcap_b"]
print("total $T", round(tot/1000,2)); print([(k, n, round(v/tot*100,1)) for (k,v),n in zip(c.most_common(), [sum(1 for r in rows if r['country']==k) for k,_ in c.most_common()])])
ic=Counter(i for r in rows for i in r["indexes"]); print(ic.most_common())
print("top10 share", round(sum(r['mcap_b'] for r in rows[:10])/tot*100,1))
print(sum(1 for r in rows if r['country']=='USA'))
