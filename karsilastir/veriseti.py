"""Dondurulmuş Türkçe benchmark'ı okur (veri/benchmark_tr.json).

Kaynak jev-test/benchmark/veriseti.py; kopyayı `araclar/veriseti_aktar.py` üretir.
JSON'dan okumanın sebebi: bu proje jev-test olmadan da koşsun ve ölçüm sabit
kalsın. Kaynak değişirse aktarma betiği yeniden çalıştırılır, diff'te görünür.
"""
import json
import os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOL = os.path.join(KOK, "veri", "benchmark_tr.json")


class Soru:
    """Tek bir çoktan seçmeli soru ve cevap anahtarı."""

    def __init__(self, ham):
        self.id = ham["id"]
        self.kategori = ham["kategori"]
        self.durum = ham["durum"]
        self.talimat_tr = ham["talimat_tr"]
        self.talimat_en = ham["talimat_en"]
        self.secenekler = dict(ham["secenekler"])   # sıra anlamlı
        self.dogru = ham["dogru"]
        # "aynen": kaynakta zaten çoktan seçmeliydi.
        # "cevrildi": açık uçluydu, şıklar sonradan üretildi -- ölçülen şey
        # "üretebiliyor mu" değil, "doğrusunu ayırt edebiliyor mu".
        self.donusum = ham["donusum"]
        self.not_ = ham.get("not", "")

    def talimat(self, kol):
        """kol: 'tr-q' (talimat Türkçe) | 'en-q' (talimat İngilizce).

        `durum` her iki kolda da Türkçe kalır -- ölçülen karar tam olarak
        "soruları hangi dilde yazalım".
        """
        return self.talimat_tr if kol == "tr-q" else self.talimat_en

    def as_dict(self):
        return {
            "id": self.id, "kategori": self.kategori, "durum": self.durum,
            "talimat_tr": self.talimat_tr, "talimat_en": self.talimat_en,
            "secenekler": self.secenekler, "dogru": self.dogru,
            "donusum": self.donusum, "not": self.not_,
        }


class VeriSeti:
    def __init__(self, ham):
        self.kaynak = ham.get("kaynak", "")
        self.not_ = ham.get("not", "")
        self.kapsam_disi = ham.get("kapsam_disi", {})
        self.sorular = [Soru(s) for s in ham["sorular"]]

    def __len__(self):
        return len(self.sorular)

    def __iter__(self):
        return iter(self.sorular)

    def bul(self, soru_id):
        for s in self.sorular:
            if s.id == soru_id:
                return s
        return None

    @property
    def kategoriler(self):
        return sorted({s.kategori for s in self.sorular})


def yukle(yol=YOL):
    if not os.path.exists(yol):
        raise SystemExit(
            "Veri seti yok: %s\nÜretmek için: python araclar/veriseti_aktar.py" % yol)
    with open(yol, encoding="utf-8") as f:
        return VeriSeti(json.load(f))
