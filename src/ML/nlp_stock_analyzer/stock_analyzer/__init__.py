"""NLP-based stock analyzer: scores news across four factors with FinBERT."""

from .config import AppConfig, Company, Settings, load_config
from .factors import FACTORS, FactorGroup, build_factor_groups
from .analyzer import Analyzer, AnalysisResult, ScoredArticle, FactorResult

__all__ = [
    "AppConfig", "Company", "Settings", "load_config",
    "FACTORS", "FactorGroup", "build_factor_groups",
    "Analyzer", "AnalysisResult", "ScoredArticle", "FactorResult",
]
