"""Soru setini JSON'dan okur.

Depoda yalnız `veri/demo_tr.json` var: on soruluk, sıfırdan yazılmış bir DEMO
seti. Düzeneğin ayakta olduğunu gösterir, doğruluk ölçmez.

**Kendi setini bağla.** Aynı şemada bir JSON yaz ve göster:

    SYSTEMONE_VERISETI=/yol/benim_setim.json python web/sunucu.py

Kendi benchmark'ın başka bir biçimdeyse `araclar/veriseti_aktar.py`'yi örnek al.
Setler repoya girmek zorunda değil -- telifi belirsiz ya da özel veriyi dışarıda
tutmak için `veri/*.json` (demo hariç) bilinçli olarak gitignore'da.
"""
import json
import os

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
YOL = os.environ.get("SYSTEMONE_VERISETI") or os.path.join(KOK, "veri", "demo_tr.json")


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
            "Veri seti bulunamadı: %s\n"
            "Depoyla gelen demo seti veri/demo_tr.json'dır; kendi setini "
            "SYSTEMONE_VERISETI ile gösterebilirsin." % yol)
    with open(yol, encoding="utf-8") as f:
        return VeriSeti(json.load(f))
