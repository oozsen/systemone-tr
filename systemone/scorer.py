"""Tipli karar okuması: tek forward pass, sıfır üretilen cevap token'ı.

Yöntem (SemIf'in "direct typed logits" deseni):
  1. Seçenekleri A/B/C... harflerine eşle, modele "yalnız tek harf yaz" de.
  2. `max_tokens=1` ile tek pozisyon çalıştır.
  3. O pozisyonun `top_logprobs`'undan seçenek harflerini süz.
  4. Yalnız o küme üzerinde yeniden normalize et.

Model cevabı yazmaz; biz yazmadan önce okuruz.

Sunucuda neden ayar değişikliği gerekmiyor:
  * vLLM'de `--logprobs-mode` varsayılanı `raw_logprobs`; değerler "temperature=1.0
    gibi" döner, istekteki temperature'dan etkilenmez. Dağılım bozulmaz.
  * `--max-logprobs` varsayılanı 20; 4-6 seçenekli sorular için fazlasıyla yeterli.

raw_logprobs maskeden ÖNCE hesaplandığı için dönen liste tüm kelime dağarcığının
top-N'idir, seçenek kümesinin değil. Pratikte prompt harfleri tepeye taşır; listede
çıkmayan bir seçenek gerçekten ihmal edilebilir olasılıktadır ve `missing` alanında
raporlanır.
"""
import math
import time

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Sunucunun `--max-logprobs` varsayılanı. Daha fazlasını istemek 400 döndürür.
TOP_LOGPROBS = 20


class ScoringError(RuntimeError):
    """Yanıt beklenen biçimde değil -- genelde düşünme modu ya da eksik logprobs."""


class Decision:
    """Bir kararın sonucu: seçilen etiket, dağılım, güven ve ölçüm bilgisi."""

    def __init__(self, label, probabilities, confidence, latency_ms, missing):
        self.label = label
        self.probabilities = probabilities
        self.confidence = confidence
        self.latency_ms = latency_ms
        self.missing = missing          # top-N'de bulunamayan seçenek etiketleri

    def __repr__(self):
        return "Decision(%r, confidence=%.3f, %.0fms)" % (
            self.label, self.confidence, self.latency_ms)

    def as_dict(self):
        return {
            "label": self.label,
            "probabilities": self.probabilities,
            "confidence": self.confidence,
            "latency_ms": round(self.latency_ms, 1),
            "missing": list(self.missing),
        }


def build_messages(state, question):
    """Durum + soru + harflenmiş seçenekler -> chat mesajları."""
    lines = []
    for i, (label, description) in enumerate(question.options):
        lines.append("%s) %s — %s" % (LETTERS[i], label, description))
    letters = ", ".join(LETTERS[: len(question.options)])
    user = (
        "DURUM:\n%s\n\nSORU: %s\n\nSEÇENEKLER:\n%s\n\n"
        "Yalnızca tek bir harf yaz (%s). Başka hiçbir şey yazma."
        % (state, question.prompt, "\n".join(lines), letters)
    )
    return [
        {"role": "system",
         "content": "Sen bir sınıflandırıcısın. Yalnızca tek bir harf ile cevap verirsin."},
        {"role": "user", "content": user},
    ]


def build_body(model, messages):
    return {
        "model": model,
        "messages": messages,
        "max_tokens": 1,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": TOP_LOGPROBS,
        # Qwen3.8 düşünme modu AÇIK gelir. Kapatılmazsa ilk token bir düşünme
        # token'ı olur ve tek-token okuması anlamını yitirir. LiteLLM'in bu alanı
        # geçirdiği ölçüldü (aksi halde hiç harf bulunamazdı).
        "chat_template_kwargs": {"enable_thinking": False},
    }


def _letter_of(token):
    """' A', 'A)', '**A' -> 'A'. Harf içermeyen token için None."""
    for ch in token.strip():
        if ch.isalpha():
            return ch.upper()
    return None


def read_distribution(response, n_options):
    """top_logprobs -> {harf: olasılık}, eksik harfler, ham liste.

    Dönen dağılım HER ZAMAN `n_options` anahtar içerir; top-N'de bulunamayanlara
    pencerenin kesim değeri atanır ve `missing` içinde raporlanır. Böylece güven
    skoru sabit bir k üzerinden hesaplanır ve vakalar arasında karşılaştırılabilir
    kalır.
    """
    try:
        content = response["choices"][0]["logprobs"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ScoringError(
            "Yanıtta logprobs yok. Taşıyıcı bu alanları geçirmiyor olabilir; "
            "DockerTransport ile doğrudan vLLM'e giderek ayırt et."
        )
    if not content:
        raise ScoringError("logprobs.content boş -- model hiç token üretmemiş.")

    raw = content[0].get("top_logprobs") or []
    wanted = {LETTERS[i] for i in range(n_options)}
    best = {}
    for entry in raw:
        letter = _letter_of(entry.get("token", ""))
        if letter in wanted:
            lp = entry.get("logprob", float("-inf"))
            # Aynı harf birden çok token biçiminde gelebilir ('A', ' A'); en yükseği kalsın.
            if letter not in best or lp > best[letter]:
                best[letter] = lp

    if not best:
        raise ScoringError(
            "top_logprobs içinde hiçbir seçenek harfi yok (ilk token: %r).\n"
            "En olası sebep: düşünme modu kapanmamış -- ilk token bir düşünme token'ı."
            % (content[0].get("token"),)
        )

    missing = sorted(wanted - set(best))
    # Listede çıkmayan seçeneğe pencerenin kesim noktasını ata. Bu bir üst sınır:
    # top-N'e giremediyse olasılığı en fazla N'incininki kadardır. Amaç dağılımı
    # doğru tahmin etmek değil, k'yı seçenek sayısında SABİT tutmak -- yoksa
    # entropi log(bulunan) ile normalize edilir ve iki seçenek kaybolduğunda güven
    # sahte biçimde yükselir (tek seçenek kalırsa 1.0'a fırlar).
    if missing:
        taban = min(
            [e.get("logprob", float("-inf")) for e in raw if e.get("logprob") is not None]
            or [min(best.values())]
        )
        for k in missing:
            best[k] = taban

    top = max(best.values())
    weights = {k: math.exp(lp - top) for k, lp in best.items()}
    total = sum(weights.values())
    probs = {k: w / total for k, w in weights.items()}
    return probs, missing, raw


def confidence_from_probs(probs):
    """1 - H(p)/log(k). Laya'nın aynı adlı fonksiyonuyla birebir aynı formül,
    böylece iki yaklaşımın güven sayıları karşılaştırılabilir kalır."""
    k = len(probs)
    if k < 2:
        return 1.0
    ent = -sum(p * math.log(max(p, 1e-12)) for p in probs.values())
    return max(0.0, min(1.0, 1.0 - ent / math.log(k)))


def score(transport, model, state, question, return_raw=False):
    """Tek bir tipli kararı oku."""
    if len(question.options) > len(LETTERS):
        raise ValueError("en fazla %d seçenek desteklenir, %d verildi"
                         % (len(LETTERS), len(question.options)))
    body = build_body(model, build_messages(state, question))
    t0 = time.time()
    response = transport.complete(body)
    latency_ms = (time.time() - t0) * 1000.0

    probs, missing_letters, raw = read_distribution(response, len(question.options))
    labels = [label for label, _ in question.options]
    named = {labels[LETTERS.index(k)]: v for k, v in probs.items()}
    winner = max(named, key=named.get)

    decision = Decision(
        label=winner,
        probabilities=dict(sorted(named.items(), key=lambda kv: -kv[1])),
        confidence=confidence_from_probs(probs),
        latency_ms=latency_ms,
        missing=[labels[LETTERS.index(k)] for k in missing_letters],
    )
    return (decision, raw) if return_raw else decision
