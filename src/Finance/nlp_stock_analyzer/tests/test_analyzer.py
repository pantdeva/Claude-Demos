"""Unit tests that run offline: a fake NewsAPI client and a fake sentiment scorer.

Run from the project folder:  python -m unittest discover -s tests
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_analyzer import Analyzer, build_factor_groups, load_config  # noqa: E402
from stock_analyzer.analyzer import AnalysisResult, recency_weight  # noqa: E402
from stock_analyzer.factors import NEWSAPI_MAX_QUERY, FactorGroup  # noqa: E402
from stock_analyzer.news import Article, NewsAPIError, parse_articles  # noqa: E402
from stock_analyzer.sentiment import Sentiment  # noqa: E402

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)
CONFIG = load_config(ROOT / "config" / "companies.yaml")


def art(title, days_ago=0, url=None):
    return Article(title, "", url or f"https://ex.com/{abs(hash(title))}", "Example",
                   NOW - timedelta(days=days_ago))


class KeywordScorer:
    """Positive if the text says 'beats'/'surge', negative for 'miss'/'slump'."""

    def score(self, texts):
        out = []
        for t in texts:
            t = t.lower()
            if "beats" in t or "surge" in t:
                out.append(Sentiment(0.9, 0.05, 0.05))
            elif "miss" in t or "slump" in t:
                out.append(Sentiment(0.05, 0.9, 0.05))
            else:
                out.append(Sentiment(0.1, 0.1, 0.8))
        return out


class FakeClient:
    def __init__(self, articles, fail=False):
        self.articles, self.fail, self.queries = articles, fail, []

    def search(self, query, language, start, end, page_size=100):
        self.queries.append(query)
        if self.fail:
            raise NewsAPIError("apiKeyInvalid: bad key")
        return list(self.articles)


class TestConfig(unittest.TestCase):
    def test_loads_both_markets(self):
        self.assertIn("NVDA", CONFIG.companies)
        self.assertIn("TATASTEEL.NS", CONFIG.companies)
        self.assertEqual(CONFIG.companies["TATASTEEL.NS"].market, "India")
        self.assertAlmostEqual(sum(CONFIG.settings.weights.values()), 1.0)


class TestFactors(unittest.TestCase):
    def test_groups_cover_all_four_factors(self):
        groups = build_factor_groups(CONFIG.companies["NVDA"], CONFIG.settings)
        self.assertEqual({g.factor for g in groups},
                         {"market_sentiment", "competition", "manufacturing", "customers"})
        competitor = next(g for g in groups if g.name == "Competitor news")
        self.assertEqual(competitor.direction, -1)

    def test_whole_word_matching(self):
        g = FactorGroup("customers", "c", ("Meta",))
        self.assertTrue(g.matches("Meta raises capex"))
        self.assertFalse(g.matches("Metallurgy outlook improves"))

    def test_capitalised_terms_are_case_sensitive(self):
        g = FactorGroup("competition", "c", ("Intel", "SAIL", "iron ore"))
        self.assertTrue(g.matches("Intel cuts prices"))
        self.assertFalse(g.matches("US could stop intel sharing"))
        self.assertTrue(g.matches("SAIL output rises"))
        self.assertFalse(g.matches("Caribbean sail cruise deal"))
        self.assertTrue(g.matches("Iron Ore prices climb"))      # lowercase term: any case

    def test_exclude_and_context_from_config(self):
        groups = {g.name: g for g in build_factor_groups(CONFIG.companies["TATASTEEL.NS"],
                                                         CONFIG.settings)}
        cust = groups["Customers & end markets"]
        self.assertTrue(cust.matches("India's auto sales jump, lifting steel demand"))
        self.assertFalse(cust.matches("AI infrastructure projects strain budgets in India"))
        nv = {g.name: g for g in build_factor_groups(CONFIG.companies["NVDA"], CONFIG.settings)}
        self.assertFalse(nv["Customers & end markets"].matches("Microsoft shrinks the Xbox controller"))
        self.assertTrue(nv["Customers & end markets"].matches("Microsoft raises AI capex again"))

    def test_competitor_story_naming_company_not_flipped(self):
        nv = {g.name: g for g in build_factor_groups(CONFIG.companies["NVDA"], CONFIG.settings)}
        self.assertFalse(nv["Competitor news"].matches("Nvidia, Broadcom and Marvell stocks fall"))
        self.assertTrue(nv["Competitor news"].matches("Broadcom stock falls on AI chip outlook"))

    def test_required_terms(self):
        g = FactorGroup("competition", "r", ("NVIDIA",), 1, ("announces",))
        self.assertTrue(g.matches("NVIDIA announces new GPU"))
        self.assertFalse(g.matches("NVIDIA shares drift"))

    def test_queries_respect_length_limit(self):
        terms = tuple(f"supplier number {i}" for i in range(80))
        queries = FactorGroup("manufacturing", "m", terms, 1, ("results",)).queries()
        self.assertGreater(len(queries), 1)
        self.assertTrue(all(len(q) <= NEWSAPI_MAX_QUERY for q in queries))
        self.assertTrue(all(q.endswith("AND (results)") for q in queries))


class TestNews(unittest.TestCase):
    def test_parse_skips_removed_and_errors(self):
        payload = {"status": "ok", "articles": [
            {"title": "[Removed]", "url": "u0", "publishedAt": "2026-10-15T10:00:00Z"},
            {"title": "Tata Steel beats estimates", "url": "u1", "description": "Q2",
             "publishedAt": "2026-10-15T10:00:00Z", "source": {"name": "Mint"}},
        ]}
        arts = parse_articles(payload)
        self.assertEqual(len(arts), 1)
        self.assertEqual(arts[0].source, "Mint")
        with self.assertRaises(NewsAPIError):
            parse_articles({"status": "error", "code": "rateLimited", "message": "slow down"})


class TestNewsClient(unittest.TestCase):
    def test_request_and_cache(self):
        import tempfile
        from stock_analyzer.news import NewsAPIClient

        class Resp:
            status_code = 200

            def json(self):
                return {"status": "ok", "articles": [
                    {"title": "NVIDIA beats", "url": "u", "publishedAt": "2026-10-15T10:00:00Z"}]}

        class Session:
            calls = []

            def get(self, url, params, headers, timeout):
                self.calls.append((url, params, headers))
                return Resp()

        sess = Session()
        with tempfile.TemporaryDirectory() as tmp:
            c = NewsAPIClient("KEY", cache_dir=tmp, session=sess)
            for _ in range(2):
                arts = c.search("NVIDIA", "en", NOW - timedelta(days=7), NOW)
            self.assertEqual(len(arts), 1)
            self.assertEqual(len(sess.calls), 1)  # second call served from cache
            url, params, headers = sess.calls[0]
            self.assertTrue(url.endswith("/v2/everything"))
            self.assertEqual(headers["X-Api-Key"], "KEY")
            self.assertEqual(params["searchIn"], "title,description")
            self.assertTrue(params["to"].endswith(":00:00"))      # hour-rounded for caching
            # a run a few minutes later reuses the cached response
            c.search("NVIDIA", "en", NOW - timedelta(days=7, minutes=-5), NOW + timedelta(minutes=5))
            self.assertEqual(len(sess.calls), 1)


class TestNumpyFinBERT(unittest.TestCase):
    """Tiny random BERT saved as safetensors: checks loading, tokenising and the forward pass."""

    def test_tiny_model_runs(self):
        import json
        import struct
        import tempfile

        import numpy as np
        from stock_analyzer.finbert_numpy import NumpyFinBERTScorer

        rng = np.random.default_rng(0)
        vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "profit", "falls", "rises", "##s", "steel", "."]
        D, I, V, P = 8, 16, len(vocab), 32
        shapes = {
            "bert.embeddings.word_embeddings.weight": (V, D),
            "bert.embeddings.position_embeddings.weight": (P, D),
            "bert.embeddings.token_type_embeddings.weight": (2, D),
            "bert.embeddings.LayerNorm.gamma": (D,), "bert.embeddings.LayerNorm.beta": (D,),
            "bert.pooler.dense.weight": (D, D), "bert.pooler.dense.bias": (D,),
            "classifier.weight": (3, D), "classifier.bias": (3,),
        }
        p = "bert.encoder.layer.0."
        for n in ("query", "key", "value"):
            shapes[p + f"attention.self.{n}.weight"], shapes[p + f"attention.self.{n}.bias"] = (D, D), (D,)
        shapes.update({p + "attention.output.dense.weight": (D, D), p + "attention.output.dense.bias": (D,),
                       p + "attention.output.LayerNorm.weight": (D,), p + "attention.output.LayerNorm.bias": (D,),
                       p + "intermediate.dense.weight": (I, D), p + "intermediate.dense.bias": (I,),
                       p + "output.dense.weight": (D, I), p + "output.dense.bias": (D,),
                       p + "output.LayerNorm.weight": (D,), p + "output.LayerNorm.bias": (D,)})
        header, blobs, off = {}, [], 0
        for name, shape in shapes.items():
            arr = rng.standard_normal(shape).astype(np.float32) * 0.1
            b = arr.tobytes()
            header[name] = {"dtype": "F32", "shape": list(shape), "data_offsets": [off, off + len(b)]}
            blobs.append(b)
            off += len(b)
        hb = json.dumps(header).encode()
        cfg = {"num_attention_heads": 2, "num_hidden_layers": 1, "layer_norm_eps": 1e-12,
               "id2label": {"0": "positive", "1": "negative", "2": "neutral"}}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "model.safetensors").write_bytes(struct.pack("<Q", len(hb)) + hb + b"".join(blobs))
            (tmp / "config.json").write_text(json.dumps(cfg))
            (tmp / "vocab.txt").write_text("\n".join(vocab))
            scorer = NumpyFinBERTScorer(tmp)
            self.assertEqual(scorer.tok.encode("Steel profits rise."),
                             [2, 8, 4, 7, 1, 9, 3])   # 'rise' isn't in the tiny vocab -> [UNK]
            out = scorer.score(["Steel profit falls.", "profit rises", "steel"])
            self.assertEqual(len(out), 3)
            for s in out:
                self.assertAlmostEqual(s.positive + s.negative + s.neutral, 1.0, places=5)
            # padding must not change a sentence's result
            alone = scorer.score(["steel"])[0]
            self.assertAlmostEqual(alone.positive, out[2].positive, places=5)


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.company = CONFIG.companies["NVDA"]
        self.articles = [
            art("NVIDIA beats revenue estimates", 0),
            art("NVIDIA announces Rubin chips, shares surge", 1),
            art("AMD beats estimates on MI accelerators", 0),
            art("TSMC capacity slump hits chip supply", 2),
            art("Microsoft capex surge lifts data center spending", 1),
            art("Unrelated weather story", 0),
        ]

    def run_analysis(self, articles=None):
        client = FakeClient(self.articles if articles is None else articles)
        return Analyzer(client, KeywordScorer(), CONFIG.settings).run(self.company, 7, NOW)

    def test_factor_scores_and_directions(self):
        r = self.run_analysis()
        f = r.factors
        self.assertGreater(f["market_sentiment"].score, 0.5)
        self.assertLess(f["manufacturing"].score, 0)        # supply slump is bad
        self.assertGreater(f["customers"].score, 0.5)       # customer capex is good
        comp = {a.group: a.signed for a in f["competition"].articles}
        self.assertLess(comp["Competitor news"], 0)         # AMD beating is bad for NVDA
        self.assertGreater(comp["Company news releases"], 0)

    def test_irrelevant_articles_dropped(self):
        r = self.run_analysis()
        titles = set(r.articles_frame()["headline"])
        self.assertNotIn("Unrelated weather story", titles)

    def test_syndicated_headline_counted_once(self):
        a = art("NVIDIA beats revenue estimates", 0, url="https://a.com/1")
        b = art("NVIDIA  beats revenue estimates", 0, url="https://b.com/2")
        r = self.run_analysis([a, b])
        self.assertEqual(r.factors["market_sentiment"].n_articles, 1)

    def test_excluded_sources_dropped(self):
        spam = Article("NVIDIA RTX deal beats all prices", "", "https://deal", "Slickdeals.net", NOW)
        r = self.run_analysis(self.articles + [spam])
        self.assertNotIn("Slickdeals.net", set(r.articles_frame()["source"]))

    def test_no_duplicate_url_within_factor(self):
        r = self.run_analysis()
        urls = [a.article.url for a in r.factors["market_sentiment"].articles]
        self.assertEqual(len(urls), len(set(urls)))

    def test_composite_renormalises_missing_factors(self):
        r = self.run_analysis([art("NVIDIA beats revenue estimates", 0)])
        self.assertIsNone(r.factors["customers"].score)
        comp = r.composite(CONFIG.settings.weights)
        self.assertGreater(comp, 0.5)
        self.assertEqual(AnalysisResult.verdict(comp, CONFIG.settings), "Bullish")
        self.assertEqual(AnalysisResult.verdict(None, CONFIG.settings), "No data")

    def test_all_requests_failing_raises(self):
        client = FakeClient([], fail=True)
        with self.assertRaises(NewsAPIError):
            Analyzer(client, KeywordScorer(), CONFIG.settings).run(self.company, 7, NOW)

    def test_daily_frame(self):
        daily = self.run_analysis().daily_frame()
        self.assertEqual(set(daily.columns), {"date", "factor", "impact", "articles"})
        self.assertFalse(daily.empty)

    def test_recency_weight_halves(self):
        self.assertAlmostEqual(recency_weight(NOW - timedelta(days=3), NOW, 3), 0.5)
        self.assertAlmostEqual(recency_weight(NOW, NOW, 3), 1.0)


if __name__ == "__main__":
    unittest.main()
