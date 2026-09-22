"""Kendi soru setini bu deponun JSON şemasına çeviren ÖRNEK betik.

    python araclar/veriseti_aktar.py --kaynak /yol/kendi-repom --cikti veri/benim.json

Olduğu gibi çalışmaz -- kaynağın kendi biçimine göre `yukle()` ve alan
eşlemesini düzenlemen beklenir. Burada beklenen kaynak, içinde `SORULAR` adlı
bir liste bulunduran `benchmark/veriseti.py` modülüdür; her öğede `id`,
`kategori`, `durum`, `talimat_tr`, `talimat_en`, `secenekler`, `dogru`,
`donusum`, `not_` alanları vardır.

Çıktıyı dondurmanın anlamı: set sabit kalır, değişirse diff'te görünür. Üretilen
dosya varsayılan olarak gitignore'dadır (`veri/*.json`, demo hariç) -- telifi
belirsiz ya da özel veri kazara commit edilmesin.

Yalnız çoktan seçmeli sorular aktarılır; bu depoda `noul` primitifi yok.
"""
import argparse
import json
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIKTI = os.path.join(KOK, "veri", "benchmark_tr.json")


def yukle(kaynak):
    """<kaynak>/benchmark/veriseti.py'yi import edip SORULAR'ı döndürür."""
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
    ap = argparse.ArgumentParser(description="Soru setini bu deponun şemasına çevir")
    ap.add_argument("--kaynak", required=True, help="kaynak deponun kökü")
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
        "kaynak": args.kaynak,
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
