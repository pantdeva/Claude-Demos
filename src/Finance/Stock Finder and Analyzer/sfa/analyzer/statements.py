"""Historical financial statements (Module 13 Ch 2–3) from Yahoo's annual series.

Yahoo reports in the statement currency (often different from the trading currency:
Infosys reports in USD, trades in INR). Up to `history_years` years are used; Yahoo
usually has four. Each derived line keeps a note of how it was obtained when the
direct line is missing.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import quote

from ..config import load
from ..data import yahoo

ITEMS = """TotalRevenue CostOfRevenue GrossProfit SellingGeneralAndAdministration ResearchAndDevelopment OperatingExpense
EBITDA EBIT OperatingIncome InterestExpense PretaxIncome TaxProvision NetIncome NetIncomeCommonStockholders
ReconciledDepreciation DilutedAverageShares TotalAssets CurrentAssets Inventory AccountsReceivable
CashAndCashEquivalents CashCashEquivalentsAndShortTermInvestments GrossPPE AccumulatedDepreciation NetPPE
CurrentLiabilities AccountsPayable TotalDebt LongTermDebt CurrentDebt StockholdersEquity RetainedEarnings
OrdinarySharesNumber MinorityInterest TotalLiabilitiesNetMinorityInterest CapitalExpenditure OperatingCashFlow
FreeCashFlow ChangeInWorkingCapital DeferredIncomeTax CashDividendsPaid Goodwill OtherIntangibleAssets""".split()


def fetch(symbol: str, refresh: bool = False) -> dict:
    """{item: {year_end: value}} plus "_ccy" (statement currency), cached for 7 days."""
    def get():
        q = ",".join("annual" + t for t in ITEMS)
        p1 = int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp())
        d = yahoo._get(f"{yahoo.BASE}/ws/fundamentals-timeseries/v1/finance/timeseries/{quote(symbol)}",
                       {"type": q, "period1": p1, "period2": int(time.time())})
        if d is None:
            return None
        out, ccy = {}, None
        for r in (d.get("timeseries") or {}).get("result") or []:
            t = r["meta"]["type"][0].replace("annual", "")
            for p in r.get("annual" + t) or []:
                if p and p.get("reportedValue"):
                    out.setdefault(t, {})[p["asOfDate"]] = p["reportedValue"]["raw"]
                    ccy = ccy or p.get("currencyCode")
        out["_ccy"] = ccy
        return out
    return yahoo._cached("fund", f"{symbol}|statements", get, refresh) or {}


class Statements:
    """Years × items table with Module 13 derived lines."""

    def __init__(self, raw: dict, max_years: int | None = None):
        self.ccy = raw.get("_ccy")
        rev = raw.get("TotalRevenue") or {}
        years = sorted(rev)[-(max_years or load("analyzer")["history_years"]):]
        self.years = years
        self.raw = {k: v for k, v in raw.items() if not k.startswith("_")}
        self.notes: dict[str, str] = {}
        self.d = {y: self._derive(y) for y in years}

    def get(self, item, year):
        return (self.raw.get(item) or {}).get(year)

    def _first(self, year, *items):
        for it in items:
            v = self.get(year=year, item=it)
            if v is not None:
                return v, it
        return None, None

    def _derive(self, y) -> dict:
        g = lambda *it: self._first(y, *it)[0]
        row = {"revenue": g("TotalRevenue")}
        row["cogs"] = g("CostOfRevenue")
        ebit, src = self._first(y, "EBIT", "OperatingIncome")
        row["ebit"] = ebit
        da = g("ReconciledDepreciation")
        if da is None and g("EBITDA") is not None and ebit is not None:
            da = g("EBITDA") - ebit
            self.notes["da"] = "EBITDA − EBIT (no depreciation line)"
        row["da"] = abs(da) if da is not None else None
        row["ebitda"] = g("EBITDA") if g("EBITDA") is not None else \
            (ebit + row["da"] if ebit is not None and row["da"] is not None else None)
        row["interest"] = abs(g("InterestExpense") or 0.0)
        row["pbt"] = g("PretaxIncome")
        row["tax"] = g("TaxProvision")
        row["pat"] = g("NetIncomeCommonStockholders", "NetIncome")
        row["inventory"] = g("Inventory") or 0.0
        row["receivables"] = g("AccountsReceivable") or 0.0
        row["payables"] = g("AccountsPayable") or 0.0
        row["cash"] = g("CashCashEquivalentsAndShortTermInvestments", "CashAndCashEquivalents") or 0.0
        row["net_block"] = g("NetPPE")
        gross = g("GrossPPE")
        if gross is None and row["net_block"] is not None and g("AccumulatedDepreciation") is not None:
            gross = row["net_block"] + abs(g("AccumulatedDepreciation"))
        row["gross_block"] = gross
        row["debt"] = g("TotalDebt")
        if row["debt"] is None:
            row["debt"] = (g("LongTermDebt") or 0.0) + (g("CurrentDebt") or 0.0)
        row["equity"] = g("StockholdersEquity")
        row["minority"] = g("MinorityInterest") or 0.0
        row["total_assets"] = g("TotalAssets")
        row["capex"] = abs(g("CapitalExpenditure")) if g("CapitalExpenditure") is not None else None
        row["cfo"] = g("OperatingCashFlow")
        row["dividends"] = abs(g("CashDividendsPaid") or 0.0)
        row["deferred_tax"] = g("DeferredIncomeTax") or 0.0
        row["shares"] = g("OrdinarySharesNumber", "DilutedAverageShares")
        row["current_assets"] = g("CurrentAssets")
        row["current_liabilities"] = g("CurrentLiabilities")
        return row

    def series(self, key) -> list:
        return [self.d[y][key] for y in self.years]

    def last(self, key):
        for y in reversed(self.years):
            v = self.d[y][key]
            if v is not None:
                return v
        return None

    @property
    def is_financial_layout(self) -> bool:
        """Banks/insurers: no EBIT or current-asset split in the statements."""
        return all(self.d[y]["ebit"] is None for y in self.years) or \
            all(self.d[y]["current_assets"] is None for y in self.years)

    def usable(self) -> tuple[bool, str]:
        if len(self.years) < 2:
            return False, f"only {len(self.years)} year(s) of statements"
        if self.last("revenue") in (None, 0):
            return False, "no revenue"
        if self.last("shares") in (None, 0):
            return False, "no share count"
        return True, "ok"
