"""İki karar motoru, tek arayüz: `karar(durum, talimat, secenekler) -> Karar`.

    Jev     TypeSafe'in barındırdığı System One modeli. Olasılık dağılımını
            doğrudan döndürür; biz logit okumayız, API zaten tipli cevap verir.
    Spark   DGX Spark'taki vLLM. Model cevabı yazmaz; tek pozisyonun logit'leri
            okunur (systemone.score).

İkisi de aynı `state` ve aynı şık kümesini görür, aynı Karar tipini döndürür --
karşılaştırmanın anlamlı olması buna bağlı.

Neyin karşılaştırılabilir OLMADIĞI:

  * Güven. İki taraf da 0..1 arası bir sayı veriyor ama aynı şeyi ölçmüyorlar:
    Jev'in `confidence` alanı kendi tanımı, bizimki `1 - H(p)/log k`. Aynı ölçekte
    çizilebilirler, birebir eşitlenemezler. Karşılaştırılabilir olan, her birinin
    KENDİ içinde doğruyu yanlıştan ayırıp ayırmadığı (kalibrasyon tablosu).
  * Maliyet. Jev token başına faturalanır; Spark kendi donanımımızda koşuyor,
    marjinal ücreti yok. "$0.00" ucuz demek değil, ölçülmüyor demek.

Bağımlılık yok: Jev'e de stdlib `urllib` ile gidilir (jev-test `requests`
kullanıyor, bu proje kullanmıyor).
"""
import json
import time
import urllib.error
import urllib.request

from systemone.questions import Choice
from systemone.scorer import LETTERS, score
from systemone.transport import LiteLLMTransport, TransportError


class MotorHatasi(RuntimeError):
    """Motor cevap veremedi: ağ, auth, ya da beklenmeyen gövde."""


class Karar:
    """Tek bir motorun tek bir soruya verdiği cevap."""

    def __init__(self, motor, etiket, olasiliklar, guven, gecikme_ms,
                 maliyet=None, maliyet_tahmini=False, model=None, notlar=(),
                 pencerede=None):
        self.motor = motor
        self.etiket = etiket
        self.olasiliklar = olasiliklar      # {şık: olasılık}, toplamı 1
        self.guven = guven
        self.gecikme_ms = gecikme_ms
        self.maliyet = maliyet              # USD, ya da None (ölçülmüyor)
        self.maliyet_tahmini = maliyet_tahmini
        self.model = model
        self.notlar = list(notlar)          # okuma hakkında uyarılar
        # Kaç şık top-N penceresinde GERÇEKTEN görüldü. Logit okumasında bu
        # sayı 2'nin altına düşerse güven ölçülmüş değildir: rakipler pencereye
        # girmediği için entropi neredeyse sıfır çıkar ve güven 1.0'a yapışır.
        # Jev'de her zaman tüm şıklar döner, orada None (konu dışı).
        self.pencerede = pencerede

    def __repr__(self):
        return "Karar(%s, %r, guven=%.3f, %.0fms)" % (
            self.motor, self.etiket, self.guven, self.gecikme_ms)

    def as_dict(self):
        return {
            "motor": self.motor,
            "etiket": self.etiket,
            "olasiliklar": self.olasiliklar,
            "guven": self.guven,
            "gecikme_ms": round(self.gecikme_ms, 1),
            "maliyet": self.maliyet,
            "maliyet_tahmini": self.maliyet_tahmini,
            "model": self.model,
            "notlar": self.notlar,
            "pencerede": self.pencerede,
        }

    @property
    def guven_olculdu(self):
        """Güven gerçekten ölçüldü mü, yoksa pencere darlığının ürünü mü?

        En az iki şık pencerede görülmediyse dağılım karşılaştırma içermez:
        güven yüksek çıkar ama bu 'model emin' değil, 'rakipleri göremedik'
        demektir.
        """
        return self.pencerede is None or self.pencerede >= 2


# --------------------------------------------------------------------------- Jev


class JevMotoru:
    """TypeSafe System One -- https://api.typesafe.ai/v1/systemone

    Anahtar `TYPESAFE_API_KEY`. Gövde jev-test/jev.py ile birebir aynı; tek fark
    `requests` yerine `urllib`. Cevap `answers.<id>.probabilities` içinde şık
    adlarıyla gelir, yani harf eşlemesi yok -- Spark tarafındaki A/B/C dolambacı
    burada hiç yaşanmıyor.
    """

    URL = "https://api.typesafe.ai/v1/systemone"
    # jev-1.13: milyon girdi token'ı başına $0.042, çıktı ücretsiz
    # (docs.typesafe.ai/models). Native API ücreti raporlamıyor, token'dan hesaplıyoruz.
    USD_GIRDI_TOKEN = 0.042 / 1_000_000

    ad = "jev"

    def __init__(self, api_key, model="jev-latest", timeout=60.0):
        if not api_key:
            raise MotorHatasi(
                "TYPESAFE_API_KEY yok. `.env` dosyasına ekle (.env.example'a bak). "
                "Anahtar: https://console.typesafe.ai/"
            )
        if model.startswith("~") or "/" in model:
            raise MotorHatasi(
                "Model %r bir OpenRouter slug'ı; native route'ta 'jev-latest' ya da "
                "'jev-1.13.0' gibi sabitlenmiş bir id kullan." % model
            )
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def __repr__(self):
        return "JevMotoru(%s)" % self.model

    def _istek(self, govde):
        req = urllib.request.Request(
            self.URL, data=json.dumps(govde).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detay = e.read().decode("utf-8", "replace")[:400]
            ipucu = ""
            if e.code == 401:
                ipucu = "\nTYPESAFE_API_KEY geçersiz ya da süresi dolmuş."
            elif e.code == 422:
                ipucu = "\n422 gövde hatasıdır; tekrar denemek düzeltmez."
            raise MotorHatasi("Jev HTTP %d: %s%s" % (e.code, detay, ipucu))
        except urllib.error.URLError as e:
            raise MotorHatasi("Jev'e bağlanılamadı: %s" % (e.reason,))
        except json.JSONDecodeError:
            raise MotorHatasi("Jev'den JSON gelmedi.")

    def karar(self, durum, talimat, secenekler):
        """secenekler: {şık: açıklama} -- açıklama boşsa None gönderilir."""
        criteria = {ad: (ack or None) for ad, ack in secenekler.items()}
        govde = {
            "model": self.model,
            "state": durum,
            "questions": {"cevap": {
                "type": "choice", "instructions": talimat, "criteria": criteria,
            }},
        }

        t0 = time.perf_counter()
        cevap = self._istek(govde)
        gecikme = (time.perf_counter() - t0) * 1000.0

        try:
            a = cevap["answers"]["cevap"]
            olasiliklar = dict(a["probabilities"])
            etiket = a["choice"]
            guven = a["confidence"]
        except (KeyError, TypeError):
            raise MotorHatasi("Jev cevabı beklenen biçimde değil: %s"
                              % json.dumps(cevap)[:300])

        usage = cevap.get("usage") or {}
        faturali = usage.get("cost")
        if faturali is not None:
            maliyet, tahmini = faturali, False
        elif usage.get("input_tokens") is not None:
            maliyet, tahmini = usage["input_tokens"] * self.USD_GIRDI_TOKEN, True
        else:
            maliyet, tahmini = None, False

        return Karar(
            motor=self.ad, etiket=etiket, olasiliklar=olasiliklar, guven=guven,
            gecikme_ms=gecikme, maliyet=maliyet, maliyet_tahmini=tahmini,
            model=cevap.get("model", self.model),
        )


# ------------------------------------------------------------------------- Spark


class SparkMotoru:
    """DGX Spark'taki vLLM, LiteLLM ağ geçidi üzerinden (systemone.score).

    Şıklar A/B/C... harflerine eşlenir ve tek pozisyonun logit'i okunur. Bu yüzden
    Jev'de olmayan iki şey burada var:

      * `missing` -- top-20 penceresine giremeyen şıklar. Dağılıma kesim değeriyle
        girerler, `notlar` alanında raporlanır.
      * harf yanlılığı -- şıkların SIRASI prompt'u değiştirir, dolayısıyla cevabı da
        değiştirebilir. Jev'de şıklar adlarıyla gider, sıra etkisi yoktur.
        `karar(..., ters=True)` aynı soruyu ters sırayla sorar; iki okuma
        ayrışıyorsa okunan şey içerik değil konumdur.

    Aynı ağ geçidinde birden çok model servis ediliyor (qwen3.8-27b, gemma4-26b);
    `ad` bu yüzden parametre: her model kendi motoru olarak görünür ve sonuçlar
    ayrı sütunlarda toplanır.
    """

    def __init__(self, base_url, api_key, model, ad="spark", timeout=60.0):
        self.ad = ad
        self.model = model
        self.transport = LiteLLMTransport(base_url, api_key, timeout=timeout)

    def __repr__(self):
        return "SparkMotoru(%s, %s)" % (self.ad, self.model)

    def karar(self, durum, talimat, secenekler, ters=False):
        if len(secenekler) > len(LETTERS):
            raise MotorHatasi("Spark en fazla %d şık okuyabilir, %d verildi."
                              % (len(LETTERS), len(secenekler)))
        sirali = list(secenekler.items())
        if ters:
            sirali.reverse()
        soru = Choice(talimat, [(ad, ack or "") for ad, ack in sirali])
        try:
            d = score(self.transport, self.model, durum, soru)
        except TransportError as e:
            raise MotorHatasi("%s: %s" % (self.ad, e))

        pencerede = len(secenekler) - len(d.missing)
        notlar = []
        if d.missing:
            notlar.append("top-20 penceresinde yoktu, kesim değeriyle dolduruldu: "
                          + ", ".join(d.missing))
        if pencerede < 2:
            # Tek şık görüldüyse karşılaştırma yapılmamıştır. Güven yine de
            # yüksek çıkar -- ama "model emin" değil, "rakipleri göremedik".
            notlar.append("pencerede yalnız 1 şık göründü; güven ÖLÇÜLMÜŞ DEĞİL, "
                          "pencere darlığının ürünü. Sıralama geçerli, güven değil.")

        # Jev tüm şıkları döndürür; aynı anahtar kümesini garanti edelim ki
        # arayüzde dağılımlar aynı satırlarda hizalansın.
        olasiliklar = {ad: d.probabilities.get(ad, 0.0) for ad in secenekler}

        return Karar(
            motor=self.ad, etiket=d.label, olasiliklar=olasiliklar,
            guven=d.confidence, gecikme_ms=d.latency_ms,
            maliyet=None, model=self.model, notlar=notlar,
            pencerede=pencerede,
        )
