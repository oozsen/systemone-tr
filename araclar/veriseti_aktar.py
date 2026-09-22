"""Türkçe benchmark'ı jev-test'ten JSON'a dondurur.

    python araclar/veriseti_aktar.py                    # ../jev-test varsayılan
    python araclar/veriseti_aktar.py --kaynak D:/x/jev-test

Neden kopya: `veri/benchmark_tr.json` repoya giriyor, böylece bu proje jev-test
olmadan da koşar ve ölçüm tekrar edilebilir kalır. Kaynak veri seti değişirse bu
betik yeniden çalıştırılır; diff'te ne değiştiği görünür.

Yalnız `SORULAR` (Choice) aktarılır. `NOUL_SETLERI` dışarıda: systemone-tr'de
noul primitifi yok, dolayısıyla karşılaştırılacak ikinci taraf da yok.
"""
import argparse
import json
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_KAYNAK = os.path.join(os.path.dirname(KOK), "jev-test")
CIKTI = os.path.join(KOK, "veri", "benchmark_tr.json")


def yukle(kaynak):
    """jev-test/benchmark/veriseti.py'yi import edip SORULAR'ı döndürür."""
    benchmark = os.path.join(kaynak, "benchmark")
    if not os.path.isdir(benchmark):
        raise SystemExit("benchmark klasörü yok: %s\n--kaynak ile doğru yolu ver." % benchmark)
    sys.path.insert(0, benchmark)
    try:
        import veriseti
    except ImportError as e:
        raise SystemExit("veriseti.py import edilemedi: %s" % e)
    return veriseti


def main():
    ap = argparse.ArgumentParser(description="Türkçe benchmark'ı JSON'a aktar")
    ap.add_argument("--kaynak", default=VARSAYILAN_KAYNAK, help="jev-test deposunun kökü")
    ap.add_argument("--cikti", default=CIKTI)
    args = ap.parse_args()

    v = yukle(args.kaynak)

    sorular = []
    for s in v.SORULAR:
        sorular.append({
            "id": s.id,
            "kategori": s.kategori,
            "durum": s.durum,
            "talimat_tr": s.talimat_tr,
            "talimat_en": s.talimat_en,
            # dict sırası anlamlı: Spark tarafında A/B/C harflerine bu sırayla eşlenir.
            "secenekler": {k: (val or "") for k, val in s.secenekler.items()},
            "dogru": s.dogru,
            "donusum": s.donusum,
            "not": s.not_,
        })

    paket = {
        "kaynak": "jev-test/benchmark/veriseti.py",
        "not": ("Türkçe benchmark'ın Jev'e uyarlanmış hali. 'cevrildi' işaretli sorular "
                "kaynakta açık uçluydu; çoktan seçmeliye dönüştürüldü, yani ölçülen şey "
                "'üretebiliyor mu' değil 'doğrusunu ayırt edebiliyor mu'. İki grubu ayrı oku."),
        "kapsam_disi": dict(v.KAPSAM_DISI),
        "aktarilmayan": {
            "NOUL_SETLERI": ("%d set. systemone-tr'de noul primitifi yok, "
                             "karşılaştırılacak ikinci taraf da yok." % len(v.NOUL_SETLERI)),
        },
        "sorular": sorular,
    }

    os.makedirs(os.path.dirname(args.cikti), exist_ok=True)
    with open(args.cikti, "w", encoding="utf-8") as f:
        json.dump(paket, f, ensure_ascii=False, indent=2)
        f.write("\n")

    kategoriler = {}
    for s in sorular:
        kategoriler[s["kategori"]] = kategoriler.get(s["kategori"], 0) + 1
    print("%d soru -> %s" % (len(sorular), args.cikti))
    for k, n in sorted(kategoriler.items(), key=lambda kv: -kv[1]):
        print("  %-14s %d" % (k, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
