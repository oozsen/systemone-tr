"""Türkçe benchmark'ı üç motorda koşturup terminale raporlar.

    python -m karsilastir.kosu                  # jev + qwen + gemma, kol tr-q
    python -m karsilastir.kosu --kol en-q       # talimatlar İngilizce
    python -m karsilastir.kosu --motor spark --motor gemma   # Jev'i atla
    python -m karsilastir.kosu --jsonl cikti.jsonl

Web arayüzüyle (`web/sunucu.py`) aynı `rapor` fonksiyonlarını çağırır; iki yerde
görünen sayı aynı koddan gelir. Fark yalnız sunumda.

Bu bir ÜRETİM DOĞRULUK ÖLÇÜMÜ DEĞİLDİR: 19 soru, held-out bölünmüş değil, ve
soruların çoğu açık uçludan çoktan seçmeliye dönüştürülmüş.
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

from systemone import load_config

from . import rapor, veriseti
from .motor import JevMotoru, MotorHatasi, SparkMotoru

ETIKET = {"jev": "Jev (typesafe.ai)", "spark": "Spark / Qwen", "gemma": "Spark / Gemma"}
# Tablo başlıkları için: iki Spark kolu da "Spark" diye görünmesin.
KISA = {"jev": "Jev", "spark": "Qwen", "gemma": "Gemma"}
# Spark kolları aynı ağ geçidini, farklı modelleri kullanır.
SPARK_MODELLERI = {"spark": "model", "gemma": "gemma_model"}


def motorlari_kur(cfg, istenen):
    motorlar = {}
    for ad in istenen:
        try:
            if ad == "jev":
                motorlar["jev"] = JevMotoru(cfg["typesafe_api_key"], cfg["jev_model"])
            else:
                if not cfg["api_key"]:
                    raise MotorHatasi("SYSTEMONE_API_KEY yok (.env: %s)" % cfg["env_path"])
                motorlar[ad] = SparkMotoru(
                    cfg["base_url"], cfg["api_key"], cfg[SPARK_MODELLERI[ad]], ad=ad)
        except MotorHatasi as e:
            print("  ! %s devre dışı — %s" % (ad, e))
    return motorlar


def _hucre(h):
    if not h or not h["n"]:
        return "%14s" % "—"
    return "%7s %5.1f%%" % ("%d/%d" % (h["dogru"], h["n"]), h["oran"] * 100)


def _tablo(baslik, birinci_sutun, satirlar, motorlar, anahtar):
    print("\n%s" % baslik)
    print("  %-22s" % "" + "".join("%14s" % KISA.get(m, m) for m in motorlar))
    print("  " + "-" * (22 + 14 * len(motorlar)))
    for s in satirlar:
        print("  %-22s" % s[birinci_sutun][:22]
              + "".join(_hucre(s[anahtar].get(m)) for m in motorlar))


def main():
    ap = argparse.ArgumentParser(description="Jev / Spark karşılaştırmalı koşum")
    ap.add_argument("--kol", default="tr-q", choices=["tr-q", "en-q"])
    ap.add_argument("--motor", action="append", choices=["jev", "spark", "gemma"])
    ap.add_argument("--jsonl", help="her yargıyı bu dosyaya da yaz")
    args = ap.parse_args()

    for akis in (sys.stdout, sys.stderr):
        if akis.encoding and akis.encoding.lower() != "utf-8":
            try:
                akis.reconfigure(encoding="utf-8")
            except Exception:
                pass

    vs = veriseti.yukle()
    motorlar = motorlari_kur(load_config(), args.motor or ["jev", "spark", "gemma"])
    if not motorlar:
        print("\nHiçbir motor kurulamadı.")
        return 2

    print("kol=%s  %d soru  motorlar=%s" % (args.kol, len(vs), list(motorlar)))
    print("\n  %-22s %-26s %-26s" % ("soru", "beklenen", "bulunan"))
    print("  " + "-" * 100)

    motor_sonuclari = {m: [] for m in motorlar}
    hata_sayisi = 0

    with ThreadPoolExecutor(max_workers=len(motorlar)) as havuz:
        for soru in vs:
            isler = {m: havuz.submit(mo.karar, soru.durum, soru.talimat(args.kol),
                                     soru.secenekler)
                     for m, mo in motorlar.items()}
            parcalar = []
            for m, f in isler.items():
                try:
                    s = rapor.Sonuc(soru, f.result(), args.kol)
                except MotorHatasi as e:
                    hata_sayisi += 1
                    parcalar.append("%s: HATA %s" % (m, str(e)[:60]))
                    continue
                motor_sonuclari[m].append(s)
                parcalar.append("%s %s %.2f" % (
                    "ok " if s.dogru else "YNL", s.karar.etiket[:20], s.karar.guven))
            print("  %-22s %-26s %s" % (soru.id[:22], soru.dogru[:26], " | ".join(parcalar)))

    motor_sonuclari = {m: ss for m, ss in motor_sonuclari.items() if ss}
    if not motor_sonuclari:
        print("\nHiçbir soru cevaplanamadı.")
        return 1

    r = rapor.tam_rapor(motor_sonuclari)
    ms = list(motor_sonuclari)

    print("\n" + "=" * 74)
    print("Özet")
    print("=" * 74)
    for m in ms:
        o = r["ozet"][m]
        ucret = "ölçülmüyor" if o["maliyet"] is None else "%s$%.6f" % (
            "~" if o["maliyet_tahmini"] else "", o["maliyet"])
        print("  %-18s %d/%d (%.1f%%)  gecikme medyan %.0f ms, en yavaş %.0f ms  ücret %s"
              % (ETIKET.get(m, m), o["dogru"], o["n"], o["oran"] * 100,
                 o["gecikme_medyan"], o["gecikme_max"], ucret))

    _tablo("Kategori bazında doğruluk", "kategori", r["kategori"], ms, "hucreler")
    _tablo("Soru kaynağına göre", "etiket", r["donusum"], ms, "hucreler")
    print("\n  Dönüştürülmüş sorularda ölçülen şey 'üretebiliyor mu' değil,")
    print("  'doğrusunu ayırt edebiliyor mu'. İki satırı ayrı oku.")

    _tablo("Kalibrasyon — güven kovasına göre doğruluk",
           "kova", r["kalibrasyon"]["kovalar"], ms, "hucreler")
    print()
    for m in ms:
        a = r["kalibrasyon"]["ayrisma"][m]
        if a["fark"] is None:
            print("  %-18s ortalama güven farkı ölçülemedi (%s)"
                  % (ETIKET.get(m, m), "hiç yanlış yok" if not a["yanlis_sayisi"] else "veri yok"))
        else:
            print("  %-18s ortalama güven — doğrularda %.2f, yanlışlarda %.2f  (fark %+.3f)"
                  % (ETIKET.get(m, m), a["dogruda"], a["yanlista"], a["fark"]))
        if a["guven_olculmeyen"]:
            print("  %-18s ! %d/%d yargıda rakip şıklar top-20 penceresine hiç girmedi."
                  % ("", a["guven_olculmeyen"], r["ozet"][m]["n"]))
            print("  %-18s   O satırlarda güven ÖLÇÜLMÜŞ DEĞİL; yukarıdaki kovalar"
                  % "")
            print("  %-18s   bu motor için okunamaz. Sıralama/doğruluk geçerli." % "")
    print("\n  Fark ne kadar büyükse güven eşiği o kadar işe yarar. Sıfıra yakınsa")
    print("  eşikleme çalışmaz ve her kararın insana sorulması gerekir.")
    print("  Motorların güven sayıları AYNI ŞEY DEĞİLDİR; her biri yalnız kendi")
    print("  içinde okunur (bkz. karsilastir/motor.py).")

    if r["anlasmazlik"]:
        print("\n" + "=" * 74)
        print("Motorların ayrıştığı sorular (%d)" % len(r["anlasmazlik"]))
        print("=" * 74)
        for a in r["anlasmazlik"]:
            print("\n  %s  [%s]  anahtar: %s" % (a["soru_id"], a["kategori"], a["beklenen"]))
            for m in ms:
                h = a["hucreler"][m]
                print("    %-18s %s %-28s guven %.2f"
                      % (ETIKET.get(m, m), "ok " if h["dogru"] else "YNL",
                         h["etiket"][:28], h["guven"]))

    if args.jsonl:
        with open(args.jsonl, "w", encoding="utf-8") as f:
            for ss in motor_sonuclari.values():
                for s in ss:
                    f.write(json.dumps(s.as_dict(), ensure_ascii=False) + "\n")
        print("\n  yargılar yazıldı: %s" % args.jsonl)

    if hata_sayisi:
        print("\n  %d istek başarısız oldu; yukarıdaki sayılar eksik veriye dayanıyor." % hata_sayisi)

    print("\n  %d soru bir doğruluk ölçümü değildir: held-out bölünmüş değil ve" % len(vs))
    print("  kapsam dışı bırakılanlar var (%s)." % (", ".join(vs.kapsam_disi) or "—"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
