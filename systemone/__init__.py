"""systemone-tr: mevcut vLLM'den tipli karar okuması, Türkçe odaklı.

Model cevabı üretmez; üretmeden önce seçeneklerin logit'leri okunur.

    from systemone import LiteLLMTransport, questions, score

    t = LiteLLMTransport("http://10.10.104.33:4000/v1", api_key="sk-...")
    d = score(t, "qwen3.8-27b", "Faturamda iki kez ücret alınmış.", questions.departman())
    d.label, d.confidence        # -> ('faturalama', 0.993)
"""
from .config import load as load_config
from .questions import Choice, departman, aciliyet, SMOKE_CASES
from .scorer import (
    Decision,
    ScoringError,
    confidence_from_probs,
    read_distribution,
    score,
)
from .transport import DockerTransport, LiteLLMTransport, TransportError

__version__ = "0.1.0"
__all__ = [
    "Choice",
    "Decision",
    "DockerTransport",
    "LiteLLMTransport",
    "ScoringError",
    "TransportError",
    "SMOKE_CASES",
    "aciliyet",
    "confidence_from_probs",
    "departman",
    "load_config",
    "read_distribution",
    "score",
    "__version__",
]
