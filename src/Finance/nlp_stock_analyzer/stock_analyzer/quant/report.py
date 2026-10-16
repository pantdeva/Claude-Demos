"""Render the quant comparison results as a self-contained HTML dashboard."""

from __future__ import annotations

import json

TEMPLATE = r"""<title>__TICKER__ Model Comparison</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600&display=swap">
<style>
/* Layout: trading-desk report. Verdict first, then one horizon at a time, then today's forecasts and method. */
:root{
  --bg:#f3f5f8; --surface:#ffffff; --ink:#15202b; --muted:#5a6676; --line:#dbe1e8;
  --accent:#2c56c9; --accent-soft:#e3eafb; --amber:#b9720b; --good:#1d7f55; --bad:#b8352a;
  --font-display:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;
  --font-body:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-data:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Menlo,monospace;
  --s1:#2c56c9; --s2:#b9720b; --s3:#1d7f55; --s4:#8a3fb8; --s5:#c2410c; --s6:#0e7490; --s7:#be185d; --s8:#15202b; --s9:#7b8794;
}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
  --bg:#0e1319; --surface:#151c24; --ink:#e5eaf0; --muted:#94a1b0; --line:#26303b;
  --accent:#7fa2ff; --accent-soft:#1c2a47; --amber:#e3a33c; --good:#4cc28f; --bad:#f07264;
  --s1:#7fa2ff; --s2:#e3a33c; --s3:#4cc28f; --s4:#c18ae8; --s5:#fb8b4e; --s6:#4fc3dc; --s7:#f472b6; --s8:#e5eaf0; --s9:#7b8794;
  color-scheme:dark}}
:root[data-theme="dark"]{
  --bg:#0e1319; --surface:#151c24; --ink:#e5eaf0; --muted:#94a1b0; --line:#26303b;
  --accent:#7fa2ff; --accent-soft:#1c2a47; --amber:#e3a33c; --good:#4cc28f; --bad:#f07264;
  --s1:#7fa2ff; --s2:#e3a33c; --s3:#4cc28f; --s4:#c18ae8; --s5:#fb8b4e; --s6:#4fc3dc; --s7:#f472b6; --s8:#e5eaf0; --s9:#7b8794;
  color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.55 var(--font-body);
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 48px}
.wrap{max-width:1080px;margin:0 auto;display:flex;flex-direction:column;gap:28px}
h1,h2,h3{font-family:var(--font-display);font-weight:600;text-wrap:balance;margin:0;letter-spacing:.005em}
h1{font-size:clamp(28px,5vw,40px);line-height:1.1}
h2{font-size:22px}
h3{font-size:15px;font-family:var(--font-body)}
p{margin:0;max-width:68ch}
.muted{color:var(--muted)}
.eyebrow{font:500 11px/1 var(--font-data);letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.num{font-family:var(--font-data);font-variant-numeric:tabular-nums}
header{display:flex;flex-direction:column;gap:10px}
.meta{display:flex;flex-wrap:wrap;gap:6px 18px;font:13px var(--font-data);color:var(--muted)}
section{display:flex;flex-direction:column;gap:14px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:18px}
.verdicts{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.verdict{display:flex;flex-direction:column;gap:12px}
.verdict .pick{font:600 22px/1.2 var(--font-display)}
.kv{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.kv div{display:flex;flex-direction:column;gap:2px;min-width:0}
.kv .v{font:500 16px var(--font-data);font-variant-numeric:tabular-nums}
.kv .k{font-size:12px;color:var(--muted)}
.vs{font-size:13px;color:var(--muted)}
.pill{display:inline-block;font:500 11px/1 var(--font-data);padding:4px 7px;border-radius:999px;letter-spacing:.04em}
.pill.good{background:color-mix(in srgb,var(--good) 16%,transparent);color:var(--good)}
.pill.bad{background:color-mix(in srgb,var(--bad) 16%,transparent);color:var(--bad)}
.pill.neutral{background:var(--accent-soft);color:var(--accent)}
.notes{display:flex;flex-direction:column;gap:8px;margin:0;padding-left:18px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line)}
.tabs button{font:600 14px var(--font-body);color:var(--muted);background:none;border:0;padding:10px 14px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}
.tabs button[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.tabs button:focus-visible,.legend button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.scroll{overflow-x:auto;min-width:0}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{font:500 11px var(--font-data);letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
th:first-child,td:first-child{text-align:left}
td.num,td .num{font-family:var(--font-data)}
tr.bench td{color:var(--muted)}
tr.top td:first-child{font-weight:600}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:8px;vertical-align:baseline}
.legend{display:flex;flex-wrap:wrap;gap:6px}
.legend button{display:flex;align-items:center;gap:6px;font:12.5px var(--font-body);color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:999px;padding:4px 10px;cursor:pointer}
.legend button[aria-pressed="false"]{opacity:.4}
svg text{fill:var(--muted);font:11px var(--font-data)}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
.bar{position:relative;height:14px;min-width:160px}
.bar .rng{position:absolute;top:5px;height:4px;border-radius:2px;background:var(--accent);opacity:.45}
.bar .med{position:absolute;top:1px;width:3px;height:12px;background:var(--accent);border-radius:1px}
.bar .now{position:absolute;top:-2px;width:1px;height:18px;background:var(--ink);opacity:.6}
.small{font-size:12.5px}
details summary{cursor:pointer;font-weight:600}
@media (max-width:520px){.kv{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (prefers-reduced-motion:no-preference){.panel{transition:border-color .2s}}
</style>

<div class="wrap">
<header>
  <span class="eyebrow">Walk-forward backtest · seven models</span>
  <h1 id="h1"></h1>
  <p class="muted" id="lede"></p>
  <div class="meta" id="meta"></div>
</header>

<section aria-labelledby="v-h">
  <h2 id="v-h">Verdict</h2>
  <div class="verdicts" id="verdicts"></div>
  <div class="panel" id="notes-panel" hidden><h3>What the backtest says</h3><ul class="notes" id="notes"></ul></div>
</section>

<section aria-labelledby="bt-h">
  <h2 id="bt-h">Backtest by horizon</h2>
  <div class="tabs" role="tablist" id="tabs"></div>
  <div class="panel">
    <div style="display:flex;flex-direction:column;gap:10px">
      <h3 id="eq-title">Growth of $1 (log scale)</h3>
      <div class="legend" id="legend"></div>
      <div class="scroll"><svg id="eq" viewBox="0 0 900 340" role="img" aria-label="Equity curves" style="width:100%;min-width:560px;height:auto"></svg></div>
    </div>
  </div>
  <div class="panel"><h3>Strategy results</h3><p class="small muted" style="margin:4px 0 10px">Each model sets an allocation between the stock and cash every month, held for the horizon. <b>Sized</b> scales the position by expected excess return over variance; <b>signal</b> is all-in when the model gives better than even odds of beating cash. MPT also uses the market index.</p><div class="scroll"><table id="strat"></table></div></div>
  <div class="panel"><h3>Forecast accuracy</h3><p class="small muted" style="margin:4px 0 10px">Hit rate: called "beats cash" correctly. 90% coverage should be near 90%. CRPS scores the whole forecast distribution; lower is better.</p><div class="scroll"><table id="skill"></table></div></div>
</section>

<section aria-labelledby="f-h">
  <h2 id="f-h">Forecasts from today</h2>
  <p class="muted" id="f-lede"></p>
  <div class="panel"><div class="scroll"><table id="fc"></table></div><p class="small muted" style="margin-top:8px">Bar: 5th–95th percentile price; tick: median; thin line: today's price.</p></div>
  <div class="grid2">
    <div class="panel"><h3>Black-Scholes-Merton option prices</h3><p class="small muted" style="margin:4px 0 10px">At-the-money European options, priced with the GARCH volatility forecast. No live option quotes were used, so these are model prices, not market prices.</p><div class="scroll"><table id="opt"></table></div></div>
    <div class="panel" id="mpt-panel"><h3>Mean-variance portfolio (MPT)</h3><p class="small muted" style="margin:4px 0 10px" id="mpt-lede"></p><div class="scroll"><svg id="frontier" viewBox="0 0 420 240" role="img" aria-label="Efficient frontier" style="width:100%;min-width:300px;height:auto"></svg></div></div>
  </div>
  <div class="panel" id="sent-panel" hidden><h3>News sentiment (context only)</h3><p class="small" id="sent"></p></div>
</section>

<section aria-labelledby="m-h">
  <h2 id="m-h">Method and limits</h2>
  <div class="panel"><details open><summary>How the test works</summary><ul class="notes small" style="margin-top:10px" id="method"></ul></details></div>
  <div class="panel"><details><summary>Model parameters fitted today</summary><div class="scroll" style="margin-top:10px"><table id="params"></table></div></details></div>
  <p class="small muted">For research and education only. Not investment advice.</p>
</div>

<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const pct = (v, d=1) => v == null ? "—" : (v*100).toFixed(d) + "%";
const sgn = (v, d=1) => v == null ? "—" : (v>0?"+":"") + (v*100).toFixed(d) + "%";
const f2 = v => v == null ? "—" : v.toFixed(2);
const money = v => v == null ? "—" : "$" + (v >= 1000 ? v.toLocaleString(undefined,{maximumFractionDigits:0}) : v.toFixed(2));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const COLORS = ["--s1","--s2","--s3","--s4","--s5","--s6","--s7","--s8","--s9"];
const H = Object.keys(D.backtest.horizons);
const order = [];
H.forEach(h => Object.keys(D.backtest.horizons[h].curves).forEach(k => { if(!order.includes(k)) order.push(k); }));
const colorOf = name => css(COLORS[order.indexOf(name) % COLORS.length]);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

$("h1").textContent = `${D.ticker}: which model wins over 3 months and 1 year?`;
$("lede").textContent = `Seven quantitative models forecast ${D.ticker} at monthly intervals using only the data available at the time, then trade on their own forecasts. Results are compared against simply holding the stock.`;
const p = D.backtest.period;
$("meta").innerHTML = [
  `Data ${D.data.first} → ${D.data.last}${D.data.source?` (${D.data.source})`:''}`, `${D.data.days.toLocaleString()} trading days`,
  `${D.data.origins} forecast dates`, `Fit window ${Math.round(D.data.window/252)} years`,
  `Trading ${p[0]} → ${p[1]}`].map(x=>`<span>${esc(x)}</span>`).join("");

// ---------- verdicts
const bench = (h) => D.backtest.horizons[h].strategies.find(s => s.model.startsWith("Buy & hold") && s.model.includes(D.ticker));
$("verdicts").innerHTML = H.map(h => {
  const hz = D.backtest.horizons[h], b = hz.best.best_risk_adjusted, g = hz.best.best_growth, bh = bench(h);
  const skill = [...hz.skill].sort((a,b)=>a.crps-b.crps)[0];
  const beat = b.sharpe > bh.sharpe;
  return `<div class="panel verdict">
    <span class="eyebrow">${esc(h)} horizon</span>
    <div class="pick">${esc(b.model)} <span class="muted" style="font-size:15px">(${esc(b.rule)})</span></div>
    <span><span class="pill ${beat?'good':'bad'}">${beat?'beat':'trailed'} buy &amp; hold on risk-adjusted return</span></span>
    <div class="kv">
      <div><span class="v">${f2(b.sharpe)}</span><span class="k">Sharpe</span></div>
      <div><span class="v">${pct(b.cagr)}</span><span class="k">Yearly growth</span></div>
      <div><span class="v">${pct(b.max_drawdown,0)}</span><span class="k">Worst drop</span></div>
      <div><span class="v">${pct(b.avg_exposure,0)}</span><span class="k">Avg. in stock</span></div>
    </div>
    <span class="vs">Buy &amp; hold ${esc(D.ticker)}: Sharpe ${f2(bh.sharpe)}, ${pct(bh.cagr)} a year, worst drop ${pct(bh.max_drawdown,0)}.<br>
    Highest raw growth: ${esc(g.model)} (${esc(g.rule)}), ${pct(g.cagr)} a year. Most accurate forecasts: ${esc(skill.model)}.</span>
  </div>`;}).join("");
if (D.notes && D.notes.length){ $("notes-panel").hidden = false; $("notes").innerHTML = D.notes.map(n=>`<li>${esc(n)}</li>`).join(""); }

// ---------- tabs
let current = H[0];
const hidden = new Set();
$("tabs").innerHTML = H.map((h,i)=>`<button role="tab" id="tab-${i}" aria-selected="${i===0}">${esc(h)}</button>`).join("");
H.forEach((h,i)=> $("tab-"+i).addEventListener("click", ()=>{ current=h; H.forEach((_,j)=>$("tab-"+j).setAttribute("aria-selected", j===i)); drawHorizon(); }));

function drawEquity(curves){
  const svg = $("eq"), W=900, Hh=340, L=56, R=14, T=12, B=30;
  const names = Object.keys(curves).filter(n=>!hidden.has(n));
  const dates = curves[Object.keys(curves)[0]].dates;
  let lo=Infinity, hi=-Infinity;
  names.forEach(n=>curves[n].values.forEach(v=>{ if(v>0){ lo=Math.min(lo,v); hi=Math.max(hi,v);} }));
  if(!isFinite(lo)){ svg.innerHTML=""; return; }
  const l0=Math.floor(Math.log10(lo)), l1=Math.ceil(Math.log10(hi));
  const x = i => L + (W-L-R) * i / Math.max(1, dates.length-1);
  const y = v => T + (Hh-T-B) * (1 - (Math.log10(v)-l0)/(l1-l0||1));
  let g = "";
  for(let e=l0;e<=l1;e++){ const yy=y(10**e); g+=`<line x1="${L}" x2="${W-R}" y1="${yy}" y2="${yy}" stroke="${css('--line')}"/><text x="${L-8}" y="${yy+4}" text-anchor="end">${10**e>=1? '$'+(10**e).toLocaleString() : '$'+(10**e)}</text>`; }
  const step = Math.max(1, Math.round(dates.length/8));
  for(let i=0;i<dates.length;i+=step){ g+=`<text x="${x(i)}" y="${Hh-8}" text-anchor="middle">${dates[i].slice(0,4)}</text>`; }
  names.forEach(n=>{
    const v = curves[n].values; let d="";
    v.forEach((val,i)=>{ if(val>0) d+=(d?"L":"M")+x(i).toFixed(1)+","+y(val).toFixed(1); });
    const isB = n.startsWith("Buy & hold");
    g+=`<path d="${d}" fill="none" stroke="${colorOf(n)}" stroke-width="${isB?2.4:1.6}" ${isB?'stroke-dasharray="5 4"':''}/>`;
    const last=v[v.length-1]; g+=`<circle cx="${x(v.length-1)}" cy="${y(last)}" r="3" fill="${colorOf(n)}"/>`;
  });
  svg.innerHTML = g;
}

function drawHorizon(){
  const hz = D.backtest.horizons[current];
  $("eq-title").textContent = `Growth of $1, ${current} strategies (log scale)`;
  const names = Object.keys(hz.curves);
  $("legend").innerHTML = names.map((n,i)=>`<button aria-pressed="${!hidden.has(n)}" data-n="${esc(n)}"><span class="sw" style="background:${colorOf(n)};margin:0"></span>${esc(n)}</button>`).join("");
  $("legend").querySelectorAll("button").forEach(b=>b.addEventListener("click",()=>{ const n=b.dataset.n; hidden.has(n)?hidden.delete(n):hidden.add(n); drawHorizon(); }));
  drawEquity(hz.curves);
  const rows = [...hz.strategies].sort((a,b)=> (b.sharpe??-9)-(a.sharpe??-9));
  const bestKey = hz.best.best_risk_adjusted.model + hz.best.best_risk_adjusted.rule;
  $("strat").innerHTML = `<thead><tr><th>Strategy</th><th>Rule</th><th>Sharpe</th><th>Yearly growth</th><th>Volatility</th><th>Worst drop</th><th>$1 became</th><th>Avg. in stock</th></tr></thead><tbody>` +
    rows.map(s=>`<tr class="${s.rule==='benchmark'?'bench':''} ${s.model+s.rule===bestKey?'top':''}"><td><span class="sw" style="background:${colorOf(s.model)}"></span>${esc(s.model)}</td><td>${esc(s.rule)}</td><td class="num">${f2(s.sharpe)}</td><td class="num">${pct(s.cagr)}</td><td class="num">${pct(s.vol)}</td><td class="num">${pct(s.max_drawdown,0)}</td><td class="num">${s.multiple==null?'—':s.multiple>=100?'$'+Math.round(s.multiple).toLocaleString():'$'+s.multiple.toFixed(2)}</td><td class="num">${s.rule==='benchmark'?'—':pct(s.avg_exposure,0)}${s.avg_market!=null?` <span class="muted">+ ${pct(s.avg_market,0)} index</span>`:''}</td></tr>`).join("") + "</tbody>";
  const sk = [...hz.skill].sort((a,b)=>a.crps-b.crps);
  $("skill").innerHTML = `<thead><tr><th>Model</th><th>Forecasts</th><th>Hit rate</th><th>Mean abs. error</th><th>90% coverage</th><th>90% band width</th><th>CRPS</th></tr></thead><tbody>` +
    sk.map((s,i)=>{ const cov = Math.abs(s.coverage90-0.9) <= 0.05 ? 'good' : (s.coverage90 < 0.8 || s.coverage90 > 0.97 ? 'bad':'neutral');
      return `<tr class="${i===0?'top':''}"><td><span class="sw" style="background:${colorOf(s.model)}"></span>${esc(s.model)}</td><td class="num">${s.n}</td><td class="num">${pct(s.hit_rate,0)}</td><td class="num">${pct(s.mae_log)}</td><td><span class="pill ${cov} num">${pct(s.coverage90,0)}</span></td><td class="num">${pct(s.width90,0)}</td><td class="num">${s.crps.toFixed(4)}</td></tr>`;}).join("") + "</tbody>";
}
drawHorizon();

// ---------- today's forecasts
const C = D.current;
$("f-lede").textContent = `Each model fitted on the ${Math.round(D.data.window/252)} years to ${C.as_of}. Last close ${money(C.price)}; cash yield ${pct(C.rf,2)} a year (${esc(D.data.rf_source||'US 3-month T-bill')}).`;
let lo=Infinity, hi=-Infinity;
C.models.forEach(m=>H.forEach(h=>{ lo=Math.min(lo,m.horizons[h].p05_price); hi=Math.max(hi,m.horizons[h].p95_price); }));
lo=Math.min(lo,C.price); hi=Math.max(hi,C.price);
const pos = v => ((v-lo)/(hi-lo)*100).toFixed(1)+"%";
const bar = (r) => `<div class="bar" aria-hidden="true"><div class="rng" style="left:${pos(r.p05_price)};width:calc(${pos(r.p95_price)} - ${pos(r.p05_price)})"></div><div class="med" style="left:calc(${pos(r.median_price)} - 1px)"></div><div class="now" style="left:${pos(C.price)}"></div></div>`;
$("fc").innerHTML = `<thead><tr><th>Model</th>${H.map(h=>`<th>${esc(h)}: median</th><th>5–95% range</th><th style="text-align:left">Spread</th><th>Beats cash</th><th>Suggested in stock</th>`).join("")}</tr></thead><tbody>` +
  C.models.map(m=>`<tr><td><span class="sw" style="background:${colorOf(m.model)}"></span>${esc(m.model)}</td>${H.map(h=>{ const r=m.horizons[h]; return `<td class="num">${money(r.median_price)}</td><td class="num">${money(r.p05_price)} – ${money(r.p95_price)}</td><td>${bar(r)}</td><td class="num">${pct(r.p_beat_cash,0)}</td><td class="num">${pct(r.w_sized,0)}</td>`; }).join("")}</tr>`).join("") + "</tbody>";
$("opt").innerHTML = `<thead><tr><th>Expiry</th><th>Strike</th><th>Volatility</th><th>Call</th><th>Put</th><th>Implied vol (check)</th></tr></thead><tbody>` +
  C.options.map(o=>`<tr><td>${esc(o.horizon)}</td><td class="num">${money(o.strike)}</td><td class="num">${pct(o.vol_used)}</td><td class="num">${money(o.call)}</td><td class="num">${money(o.put)}</td><td class="num">${pct(o.implied_vol_check)}</td></tr>`).join("") + "</tbody>";

if (!C.mpt) { $("mpt-panel").hidden = true; }
if (C.mpt){
  const w = C.mpt.weights;
  $("mpt-lede").innerHTML = `Best long-only mix of ${esc(D.ticker)}, ${esc(D.market_name)} and cash for risk aversion ${D.data.gamma}, from the last ${Math.round(D.data.window/252)} years: <b class="num">${pct(w[D.ticker],0)}</b> ${esc(D.ticker)}, <b class="num">${pct(w[D.market_name],0)}</b> ${esc(D.market_name)}, <b class="num">${pct(w.Cash,0)}</b> cash. Past means are a weak guide to future returns.`;
  const svg=$("frontier"), W=420, Hh=240, L=44, R=14, T=12, B=30;
  const pts = C.mpt.frontier, assets = C.mpt.assets;
  const xs = pts.map(p=>p[0]).concat(Object.values(assets).map(a=>a[0])), ys = pts.map(p=>p[1]).concat(Object.values(assets).map(a=>a[1]), [C.rf]);
  const x0=0, x1=Math.max(...xs)*1.1, y0=Math.min(0,...ys), y1=Math.max(...ys)*1.1;
  const X=v=>L+(W-L-R)*(v-x0)/(x1-x0), Y=v=>T+(Hh-T-B)*(1-(v-y0)/(y1-y0));
  let g="";
  for(let i=0;i<=4;i++){ const yv=y0+(y1-y0)*i/4, xv=x0+(x1-x0)*i/4;
    g+=`<line x1="${L}" x2="${W-R}" y1="${Y(yv)}" y2="${Y(yv)}" stroke="${css('--line')}"/><text x="${L-6}" y="${Y(yv)+4}" text-anchor="end">${(yv*100).toFixed(0)}%</text><text x="${X(xv)}" y="${Hh-10}" text-anchor="middle">${(xv*100).toFixed(0)}%</text>`; }
  g+=`<text x="${W-R}" y="${Hh-22}" text-anchor="end">risk (yearly volatility) →</text>`;
  g+=`<path d="${pts.map((p,i)=>(i?'L':'M')+X(p[0]).toFixed(1)+','+Y(p[1]).toFixed(1)).join('')}" fill="none" stroke="${css('--accent')}" stroke-width="2"/>`;
  Object.entries(assets).forEach(([k,a])=>{ g+=`<circle cx="${X(a[0])}" cy="${Y(a[1])}" r="4" fill="${css('--amber')}"/><text x="${X(a[0])-6}" y="${Y(a[1])-8}" text-anchor="end" style="fill:${css('--ink')}">${esc(k)}</text>`; });
  g+=`<circle cx="${X(0)}" cy="${Y(C.rf)}" r="4" fill="${css('--muted')}"/><text x="${X(0)+8}" y="${Y(C.rf)+4}">cash</text>`;
  svg.innerHTML=g;
}
if (D.sentiment){ const s=D.sentiment; $("sent-panel").hidden=false;
  $("sent").innerHTML = `Latest FinBERT news composite for ${esc(s.name||D.ticker)}: <b class="num">${s.composite==null?'—':(s.composite>0?'+':'')+s.composite.toFixed(2)}</b> (${esc(s.verdict)}), from news ${esc((s.window_utc||[''])[0].slice(0,10))} to ${esc((s.window_utc||['',''])[1].slice(0,10))}. News history only covers the last month, so sentiment could not be part of the ${Math.round(D.data.days/252)}-year backtest.`; }

$("method").innerHTML = [
  `Forecast dates every ${D.data.step} trading days. At each date every model is fitted on the previous ${Math.round(D.data.window/252)} years of daily returns only, so no future data leaks into a forecast.`,
  `GBM: constant drift and volatility. Black-Scholes-Merton: the risk-neutral version (drifts at the T-bill rate, volatility from an EWMA estimate), so it never expects to beat cash. GARCH(1,1) with Student-t errors: volatility that clusters. ARIMA: AR/MA order picked by AIC each month. Merton jump-diffusion: GBM plus random jumps, fitted by maximum likelihood. Monte Carlo: resamples 10-day blocks of real past returns.`,
  `Position sizing: share in stock = (expected return − cash) ÷ (${D.data.gamma} × variance), capped between 0% and 100%; no leverage, no shorting. MPT does the same across ${esc(D.ticker)}, ${esc(D.market_name)} and cash.`,
  `Each month's decision is held for the full horizon, so 3-month results average 3 overlapping tranches and 1-year results average 12. Costs and taxes are ignored.`,
  `${esc(D.ticker)} was chosen after the fact and has been one of the best-performing stocks of the period. Any model that leans long will look good here; the same test on a stock that fell would rank the models differently.`,
  `1-year forecasts give only about ${Math.round((D.data.days-D.data.window)/252)} independent years, so differences between models there are not statistically strong.`,
].map(x=>`<li>${x}</li>`).join("");
const P = C.models.map(m=>`<tr><td>${esc(m.model)}</td><td style="text-align:left;white-space:normal">${Object.entries(m.params).map(([k,v])=>`${esc(k)} <span class="num">${typeof v==='number'?(Math.abs(v)<0.01&&v!==0?v.toExponential(2):v.toFixed(3)):esc(Array.isArray(v)?v.map(x=>x.toFixed(3)).join(', '):v)}</span>`).join(' · ')}</td></tr>`).join("");
$("params").innerHTML = `<thead><tr><th>Model</th><th style="text-align:left">Fitted parameters</th></tr></thead><tbody>${P}</tbody>`;
</script>
"""


def render_dashboard(result: dict) -> str:
    data = json.dumps(result, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", data).replace("__TICKER__", result.get("ticker", "Stock"))


# ---------------------------------------------------------------- cross-stock page
_HEAD = TEMPLATE.split("<style>")[0].replace("__TICKER__ Model Comparison", "Quant Model Basket Test")
_STYLE = "<style>" + TEMPLATE.split("<style>")[1].split("</style>")[0] + """
.heat td.cell{font-family:var(--font-data);font-variant-numeric:tabular-nums;text-align:center;min-width:64px}
.heat th.rot{white-space:normal;text-align:center;min-width:64px;line-height:1.2}
.chip{display:inline-block;font:12px var(--font-body);color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 8px}
</style>"""

BASKET_BODY = r"""
<div class="wrap">
<header>
  <span class="eyebrow">Walk-forward backtest · seven models · <span id="nstocks"></span> stocks</span>
  <h1>Which model works across very different stocks?</h1>
  <p class="muted">The same test as the NVIDIA dashboard, repeated on winners, decliners, cyclicals, steady names, Indian stocks and the S&amp;P 500 itself. Every stock uses data from 1999 onward, a 5-year fitting window and monthly forecasts.</p>
  <div class="meta" id="meta"></div>
</header>

<section aria-labelledby="v-h">
  <h2 id="v-h">Verdict</h2>
  <div class="verdicts" id="verdicts"></div>
  <div class="panel" id="notes-panel" hidden><h3>What the basket says</h3><ul class="notes" id="notes"></ul></div>
</section>

<section aria-labelledby="r-h">
  <h2 id="r-h">Rankings by horizon</h2>
  <div class="tabs" role="tablist" id="tabs"></div>
  <div class="panel"><h3>Strategy league table</h3><p class="small muted" style="margin:4px 0 10px">Strategies are ranked by Sharpe ratio within each stock, then averaged. Differences are versus simply holding that stock: positive Sharpe and worst-drop differences are better; growth differences show what was given up.</p><div class="scroll"><table id="league"></table></div></div>
  <div class="panel"><h3>Sharpe ratio versus buy &amp; hold, stock by stock</h3><p class="small muted" style="margin:4px 0 10px">Green: the strategy beat holding the stock on risk-adjusted return. Red: it did worse.</p><div class="scroll"><table class="heat" id="heat"></table></div></div>
  <div class="grid2">
    <div class="panel"><h3>Best strategy per stock</h3><div class="scroll"><table id="perstock"></table></div></div>
    <div class="panel"><h3>Forecast accuracy across stocks</h3><p class="small muted" style="margin:4px 0 10px">Average CRPS rank (1 = most accurate distribution) and how many stocks each model forecast best.</p><div class="scroll"><table id="skill"></table></div></div>
  </div>
</section>

<section aria-labelledby="m-h">
  <h2 id="m-h">Method and limits</h2>
  <div class="panel"><ul class="notes small" id="method"></ul></div>
  <p class="small muted">For research and education only. Not investment advice.</p>
</section>
</div>

<script>
const D = __DATA__;
const $ = id => document.getElementById(id);
const pct = (v,d=1) => v==null ? "—" : (v*100).toFixed(d)+"%";
const sp = (v,d=1) => v==null ? "—" : (v>0?"+":"")+(v*100).toFixed(d)+" pts";
const f2 = v => v==null ? "—" : v.toFixed(2);
const s2 = v => v==null ? "—" : (v>0?"+":"")+v.toFixed(2);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const H = Object.keys(D.horizons);
const nameOf = t => (D.stocks.find(s=>s.ticker===t)||{name:t}).name;
$("nstocks").textContent = D.stocks.length;
$("meta").innerHTML = D.stocks.map(s=>`<span class="chip" title="${esc(s.group)}">${esc(s.name)}</span>`).join(" ");

$("verdicts").innerHTML = H.map(h=>{
  const hz = D.horizons[h], top = hz.ranking[0];
  const beat = hz.per_stock.filter(p=>p.beat_bh).length, n = hz.per_stock.length;
  const fc = hz.skill[0];
  return `<div class="panel verdict"><span class="eyebrow">${esc(h)} horizon</span>
    <div class="pick">${esc(top.strategy)}</div>
    <span><span class="pill neutral">best average rank: ${top.avg_rank.toFixed(1)}</span></span>
    <div class="kv">
      <div><span class="v">${top.beat_bh}/${top.stocks}</span><span class="k">Beat holding</span></div>
      <div><span class="v">${s2(top.med_d_sharpe)}</span><span class="k">Median Sharpe vs hold</span></div>
      <div><span class="v">${sp(top.med_d_dd,0)}</span><span class="k">Worst drop vs hold</span></div>
      <div><span class="v">${sp(top.med_d_cagr)}</span><span class="k">Growth vs hold / yr</span></div>
    </div>
    <span class="vs">On ${beat} of ${n} stocks the best model strategy beat buy &amp; hold on Sharpe. Most accurate forecaster overall: ${esc(fc.model)} (best on ${fc.wins} of ${n}).</span></div>`;}).join("");
if (D.notes && D.notes.length){ $("notes-panel").hidden=false; $("notes").innerHTML = D.notes.map(n=>`<li>${esc(n)}</li>`).join(""); }

let cur = H[0];
$("tabs").innerHTML = H.map((h,i)=>`<button role="tab" id="tab-${i}" aria-selected="${i===0}">${esc(h)}</button>`).join("");
H.forEach((h,i)=>$("tab-"+i).addEventListener("click",()=>{cur=h;H.forEach((_,j)=>$("tab-"+j).setAttribute("aria-selected",j===i));draw();}));

function heatColor(v){
  if (v==null) return "transparent";
  const a = Math.min(Math.abs(v)/0.4, 1) * 0.55 + 0.08;
  return `color-mix(in srgb, ${v>=0?css('--good'):css('--bad')} ${Math.round(a*100)}%, transparent)`;
}
function draw(){
  const hz = D.horizons[cur];
  $("league").innerHTML = `<thead><tr><th>Strategy</th><th>Avg. rank</th><th>Top 3</th><th>Beat holding</th><th>Median Sharpe vs hold</th><th>Median growth vs hold</th><th>Median worst drop vs hold</th><th>Avg. in stock</th></tr></thead><tbody>` +
    hz.ranking.map((r,i)=>`<tr class="${i===0?'top':''}"><td>${esc(r.strategy)}</td><td class="num">${r.avg_rank.toFixed(1)}</td><td class="num">${r.top3}/${r.stocks}</td><td><span class="pill ${r.beat_bh/r.stocks>=0.5?'good':(r.beat_bh===0?'bad':'neutral')} num">${r.beat_bh}/${r.stocks}</span></td><td class="num">${s2(r.med_d_sharpe)}</td><td class="num">${sp(r.med_d_cagr)}</td><td class="num">${sp(r.med_d_dd,0)}</td><td class="num">${pct(r.avg_exposure,0)}</td></tr>`).join("") + "</tbody>";
  const g = hz.grid;
  $("heat").innerHTML = `<thead><tr><th>Strategy</th>${g.tickers.map(t=>`<th class="rot">${esc(nameOf(t))}</th>`).join("")}</tr></thead><tbody>` +
    g.strategies.map((s,i)=>`<tr><td>${esc(s)}</td>${g.values[i].map(v=>`<td class="cell" style="background:${heatColor(v)}">${v==null?'—':s2(v)}</td>`).join("")}</tr>`).join("") + "</tbody>";
  $("perstock").innerHTML = `<thead><tr><th>Stock</th><th>Hold: growth / yr</th><th>Hold: worst drop</th><th>Best strategy</th><th>Its Sharpe vs hold</th></tr></thead><tbody>` +
    hz.per_stock.map(p=>`<tr><td>${esc(p.name)}<br><span class="small muted">${esc(p.group)}</span></td><td class="num">${pct(p.bh_cagr)}</td><td class="num">${pct(p.bh_dd,0)}</td><td style="white-space:normal">${esc(p.best||'—')}</td><td><span class="pill ${p.beat_bh?'good':'bad'} num">${f2(p.best_sharpe)} vs ${f2(p.bh_sharpe)}</span></td></tr>`).join("") + "</tbody>";
  $("skill").innerHTML = `<thead><tr><th>Model</th><th>Avg. CRPS rank</th><th>Best on</th><th>Hit rate</th><th>90% coverage</th></tr></thead><tbody>` +
    hz.skill.map((s,i)=>`<tr class="${i===0?'top':''}"><td>${esc(s.model)}</td><td class="num">${s.avg_crps_rank.toFixed(1)}</td><td class="num">${s.wins}</td><td class="num">${pct(s.hit_rate,0)}</td><td class="num">${pct(s.coverage90,0)}</td></tr>`).join("") + "</tbody>";
}
draw();
const india = D.stocks.filter(s=>s.rf_source && s.rf_source.startsWith("fixed")).map(s=>s.name);
$("method").innerHTML = [
  "Each stock: daily prices from Yahoo Finance from 1 January 1999 (or the first available date), one-day price spikes that reverse the next day removed as data errors.",
  "Every month each model is fitted on the previous 5 years only and sets an allocation for the next 3 months or 1 year. No future data is used.",
  "US stocks use the S&P 500 for MPT and US 3-month T-bills as cash." + (india.length ? ` ${india.join(" and ")} use the Sensex and a fixed 6.5% cash rate (an approximation of Indian T-bill yields, since no current series was available).` : ""),
  "The S&P 500 run skips MPT because the stock and the index are the same thing.",
  "Strategies that stayed almost entirely in cash on most stocks are left out of the league table: " + ([...new Set(H.flatMap(h=>D.horizons[h].excluded||[]))].join(", ") || "none") + ". Black-Scholes-Merton is a risk-neutral pricing model that never expects to beat cash, so it is judged on forecast accuracy only.",
  "Ranks compare model strategies within a stock; buy & hold is the yardstick, not a ranked entry. Strategies that were almost never invested are left out of the ranking.",
  "Costs, taxes and dividends beyond Yahoo's adjusted prices are ignored. With 22 years per stock, small differences between models are noise.",
].map(x=>`<li>${esc(x)}</li>`).join("");
</script>
"""


def render_basket(result: dict) -> str:
    data = json.dumps(result, separators=(",", ":"), default=float).replace("</", "<\\/")
    return _HEAD + _STYLE + BASKET_BODY.replace("__DATA__", data)
