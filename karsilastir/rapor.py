"""Koşum sonuçlarını sayıya çevirir. Saf fonksiyonlar -- ağ yok, baskı yok.

CLI (`kosu.py`) ve web arayüzü aynı fonksiyonları çağırır, böylece tabloda
görünen sayı ile terminalde görünen sayı aynı koddan gelir.

Üç şeye bakılır, ve sıralama önem sırasıdır:

1. Doğruluk. En bilinen sayı, tek başına en az işe yarayanı.
2. Kalibrasyon. Asıl soru: güven yüksekken gerçekten daha mı doğru? Mimarideki
   rol "emin olduğunda çalıştır, olmadığında insana sor" olduğu için, %70 doğru
   ama güveni doğruyu yanlıştan ayıran bir motor, %85 doğru ama güveni düz olan
   bir motordan daha kullanışlıdır.
3. Gecikme / maliyet.

Motorların güven sayıları AYNI ŞEY DEĞİLDİR (bkz. motor.py). Bu yüzden burada
hiçbir yerde "Jev'in güveni Spark'ınkinden yüksek" gibi bir kıyas yapılmaz;
her motorun güveni yalnız kendi içinde, doğruyu yanlıştan ayırma gücü olarak
değerlendirilir.
"""
import statistics

# Kalibrasyon kovaları. Üst sınır dışlayıcı; en üsttekinde 1.0 da kapsansın diye 1.01.
KOVALAR = [("≥ 0.90", 0.90, 1.01), ("0.70 – 0.90", 0.70, 0.90), ("< 0.70", 0.0, 0.70)]


class Sonuc:
    """Tek soru x tek motor."""

    def __init__(self, soru, karar, kol):
        self.soru_id = soru.id
        self.kategori = soru.kategori
        self.donusum = soru.donusum
        self.beklenen = soru.dogru
        self.kol = kol
        self.karar = karar
        self.dogru = karar.etiket == soru.dogru

    def as_dict(self):
        d = {
            "soru_id": self.soru_id, "kategori": self.kategori,
            "donusum": self.donusum, "beklenen": self.beklenen,
            "kol": self.kol, "dogru": self.dogru,
        }
        d.update(self.karar.as_dict())
        return d


def _oran(alt):
    return sum(s.dogru for s in alt) / len(alt) if alt else None


def ozet(sonuclar):
    """Bir motorun tüm koşumu tek satırda."""
    if not sonuclar:
        return {"n": 0}
    gecikmeler = [s.karar.gecikme_ms for s in sonuclar]
    maliyetli = [s.karar.maliyet for s in sonuclar if s.karar.maliyet is not None]
    # Güveni pencere darlığı yüzünden okunamayan yargılar. Bu sayı toplama
    # yaklaştıkça kalibrasyon tablosu anlamını yitirir: kovalar dolu görünür
    # ama içindeki güven "model emin" değil "rakipleri göremedik" demektir.
    olculmeyen = sum(1 for s in sonuclar if not s.karar.guven_olculdu)
    return {
        "n": len(sonuclar),
        "dogru": sum(s.dogru for s in sonuclar),
        "oran": _oran(sonuclar),
        "guven_olculmeyen": olculmeyen,
        "gecikme_medyan": statistics.median(gecikmeler),
        "gecikme_max": max(gecikmeler),
        # None = ölçülmüyor (Spark kendi donanımımızda; marjinal ücreti yok).
        "maliyet": sum(maliyetli) if maliyetli else None,
        "maliyet_tahmini": any(s.karar.maliyet_tahmini for s in sonuclar),
    }


def kategori_tablosu(motor_sonuclari):
    """{motor: [Sonuc]} -> kategori bazında doğruluk satırları."""
    kategoriler = sorted({s.kategori for ss in motor_sonuclari.values() for s in ss})
    satirlar = []
    for kat in kategoriler:
        hucreler = {}
        for motor, sonuclar in motor_sonuclari.items():
            alt = [s for s in sonuclar if s.kategori == kat]
            hucreler[motor] = {"dogru": sum(s.dogru for s in alt),
                               "n": len(alt), "oran": _oran(alt)}
        satirlar.append({"kategori": kat, "hucreler": hucreler})
    return satirlar


def donusum_tablosu(motor_sonuclari):
    """Kaynaktaki hali / dönüştürülmüş ayrımı. Ayrı okunmalı: dönüştürülmüş
    sorularda ölçülen şey 'üretebiliyor mu' değil 'ayırt edebiliyor mu'."""
    satirlar = []
    for etiket, anahtar in (("kaynaktaki hali", "aynen"), ("dönüştürülmüş", "cevrildi")):
        hucreler = {}
        for motor, sonuclar in motor_sonuclari.items():
            alt = [s for s in sonuclar if s.donusum == anahtar]
            hucreler[motor] = {"dogru": sum(s.dogru for s in alt),
                               "n": len(alt), "oran": _oran(alt)}
        satirlar.append({"etiket": etiket, "hucreler": hucreler})
    return satirlar


def kalibrasyon(motor_sonuclari):
    """Güven kovasına göre doğruluk + doğru/yanlış ortalama güven farkı."""
    kovalar = []
    for etiket, alt_sinir, ust_sinir in KOVALAR:
        hucreler = {}
        for motor, sonuclar in motor_sonuclari.items():
            alt = [s for s in sonuclar if alt_sinir <= s.karar.guven < ust_sinir]
            hucreler[motor] = {"dogru": sum(s.dogru for s in alt),
                               "n": len(alt), "oran": _oran(alt)}
        kovalar.append({"kova": etiket, "hucreler": hucreler})

    ayrisma = {}
    for motor, sonuclar in motor_sonuclari.items():
        dogrular = [s.karar.guven for s in sonuclar if s.dogru]
        yanlislar = [s.karar.guven for s in sonuclar if not s.dogru]
        od = statistics.mean(dogrular) if dogrular else None
        oy = statistics.mean(yanlislar) if yanlislar else None
        olculmeyen = sum(1 for s in sonuclar if not s.karar.guven_olculdu)
        ayrisma[motor] = {
            "dogruda": od, "yanlista": oy,
            # Satırın okunup okunamayacağını belirler; arayüz buna göre uyarır.
            "guven_olculmeyen": olculmeyen,
            "guven_okunabilir": olculmeyen < len(sonuclar) / 2 if sonuclar else False,
            # Fark ne kadar büyükse güven eşiği o kadar işe yarar. Sıfıra yakınsa
            # eşikleme çalışmaz: her kararın insana sorulması gerekir.
            "fark": (od - oy) if (od is not None and oy is not None) else None,
            "yanlis_sayisi": len(yanlislar),
        }
    return {"kovalar": kovalar, "ayrisma": ayrisma}


def anlasmazlik(motor_sonuclari):
    """Motorların ayrıştığı sorular -- bakılmaya en değer olanlar.

    Aynı soruya farklı cevap veren motorlar, hepsinin ortalama doğruluğundan
    daha fazla şey söyler: hangi soru türünün gerçekten ayırt edici olduğunu
    gösterir.
    """
    motorlar = list(motor_sonuclari)
    if len(motorlar) < 2:
        return []
    indeks = {m: {s.soru_id: s for s in ss} for m, ss in motor_sonuclari.items()}
    ortak = set.intersection(*(set(v) for v in indeks.values()))

    cikti = []
    for soru_id in sorted(ortak):
        etiketler = {m: indeks[m][soru_id].karar.etiket for m in motorlar}
        if len(set(etiketler.values())) == 1:
            continue
        cikti.append({
            "soru_id": soru_id,
            "kategori": indeks[motorlar[0]][soru_id].kategori,
            "beklenen": indeks[motorlar[0]][soru_id].beklenen,
            "hucreler": {m: {"etiket": etiketler[m],
                             "guven": indeks[m][soru_id].karar.guven,
                             "dogru": indeks[m][soru_id].dogru}
                         for m in motorlar},
        })
    return cikti


def tam_rapor(motor_sonuclari):
    """Web ve CLI'ın ortak çıktısı."""
    return {
        "ozet": {m: ozet(ss) for m, ss in motor_sonuclari.items()},
        "kategori": kategori_tablosu(motor_sonuclari),
        "donusum": donusum_tablosu(motor_sonuclari),
        "kalibrasyon": kalibrasyon(motor_sonuclari),
        "anlasmazlik": anlasmazlik(motor_sonuclari),
    }
