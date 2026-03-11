from __future__ import annotations

from dataclasses import dataclass, field

from .config import FINBERT_BATCH_SIZE, FINBERT_MODEL_NAME, MODEL_TEXT_CHAR_LIMIT

_FINBERT_RESULT_CACHE_SIZE = 4096


def _normalize_label(label: str) -> str:
    lowered = label.lower()
    if "pos" in lowered:
        return "positive"
    if "neg" in lowered:
        return "negative"
    return "neutral"


def clip_text_for_model(text: str) -> str:
    return " ".join(text.split())[:MODEL_TEXT_CHAR_LIMIT].strip()


@dataclass
class FinBertAnalyzer:
    model_name: str = FINBERT_MODEL_NAME
    _tokenizer: object | None = None
    _model: object | None = None
    _torch: object | None = None
    _id2label: dict[int, str] = field(default_factory=dict)
    _result_cache: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return self._tokenizer is not None and self._model is not None

    def _load(self) -> None:
        if self.loaded:
            return
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        self._model.eval()
        self._model.to("cpu")
        self._torch = torch
        self._id2label = {int(key): value for key, value in self._model.config.id2label.items()}

    def _cache_result(self, text: str, result: dict[str, object]) -> None:
        self._result_cache[text] = result
        if len(self._result_cache) > _FINBERT_RESULT_CACHE_SIZE:
            self._result_cache.pop(next(iter(self._result_cache)))

    def _result_from_probs(self, row: list[float]) -> dict[str, object]:
        probabilities = {
            _normalize_label(self._id2label.get(index, str(index))): float(value)
            for index, value in enumerate(row)
        }
        for key in ("positive", "neutral", "negative"):
            probabilities.setdefault(key, 0.0)
        label = max(probabilities, key=probabilities.get)
        return {
            "label": label,
            "score": float(probabilities[label]),
            "probabilities": probabilities,
        }

    def analyze_texts(self, texts: list[str]) -> list[dict[str, object]]:
        self._load()
        assert self._tokenizer is not None
        assert self._model is not None
        torch = self._torch
        results: list[dict[str, object] | None] = [None] * len(texts)
        uncached_positions: dict[str, list[int]] = {}
        uncached_texts: list[str] = []

        for index, text in enumerate(texts):
            normalized_text = clip_text_for_model(text) or "No article content available."
            cached = self._result_cache.get(normalized_text)
            if cached is not None:
                results[index] = cached
                continue
            positions = uncached_positions.get(normalized_text)
            if positions is None:
                uncached_positions[normalized_text] = [index]
                uncached_texts.append(normalized_text)
            else:
                positions.append(index)

        for start in range(0, len(uncached_texts), FINBERT_BATCH_SIZE):
            batch = uncached_texts[start : start + FINBERT_BATCH_SIZE]
            encoded = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            with torch.inference_mode():
                logits = self._model(**encoded).logits
                probs = torch.softmax(logits, dim=-1).cpu().tolist()
            for text_value, row in zip(batch, probs):
                result = self._result_from_probs(row)
                self._cache_result(text_value, result)
                for pos in uncached_positions[text_value]:
                    results[pos] = result
        fallback = {
            "label": "neutral",
            "score": 1.0,
            "probabilities": {"positive": 0.0, "neutral": 1.0, "negative": 0.0},
        }
        return [item if item is not None else fallback for item in results]


_shared_analyzer = FinBertAnalyzer()


def get_finbert_analyzer() -> FinBertAnalyzer:
    return _shared_analyzer
