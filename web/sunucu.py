"""Jev, Qwen ve Gemma'yı tarayıcıdan yan yana koşturur.

    python web/sunucu.py                 # http://127.0.0.1:8100
    python web/sunucu.py --port 9000
    python web/sunucu.py --motor spark --motor gemma   # Jev'i atla

İki şey yapar:

  Tek soru   Benchmark'tan bir soru seç (ya da kendin yaz), motorlara aynı anda
             sor, dağılımları aynı satırlarda hizalı gör.
  Tüm set    19 sorunun tamamını her motorda koştur; doğruluk, kalibrasyon,
             gecikme ve ayrıştıkları sorular tek tabloda.

API anahtarları sunucuda kalır, tarayıcıya hiçbir zaman gönderilmez.

Yalnız standart kütüphane. Motorlar `ThreadPoolExecutor` ile paralel çağrılır --
toplam gecikme en yavaşınki kadar, toplamı kadar değil.
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, KOK)

from karsilastir import JevMotoru, MotorHatasi, SparkMotoru, veriseti  # noqa: E402
from karsilastir import rapor  # noqa: E402
from systemone import load_config  # noqa: E402

ARAYUZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arayuz.html")

MOTORLAR = {}       # {ad: motor}
VERI = None
ACILIS_NOTU = []    # başlangıçta bulunan sorunlar; arayüzde gösterilir


def motorlari_kur(cfg, istenen):
    """İstenen motorları kurar. Kurulamayan motor ACILIS_NOTU'na düşer,
    sunucu yine açılır -- tek kolla da iş görülebilir."""
    motorlar = {}

    if "jev" in istenen:
        try:
            motorlar["jev"] = JevMotoru(cfg["typesafe_api_key"], cfg["jev_model"])
        except MotorHatasi as e:
            ACILIS_NOTU.append("jev devre dışı — %s" % e)

    # Spark kolları aynı ağ geçidini, farklı modelleri kullanır.
    for ad, model_anahtari in (("spark", "model"), ("gemma", "gemma_model")):
        if ad not in istenen:
            continue
        if not cfg["api_key"]:
            ACILIS_NOTU.append(
                "%s devre dışı — SYSTEMONE_API_KEY yok (.env: %s)" % (ad, cfg["env_path"]))
            continue
        try:
            motorlar[ad] = SparkMotoru(
                cfg["base_url"], cfg["api_key"], cfg[model_anahtari], ad=ad)
        except MotorHatasi as e:
            ACILIS_NOTU.append("%s devre dışı — %s" % (ad, e))

    return motorlar


def _tek_motor(motor, durum, talimat, secenekler):
    """Bir motoru çağırır; hata da bir sonuçtur, koşumu durdurmaz."""
    try:
        return motor.karar(durum, talimat, secenekler).as_dict()
    except MotorHatasi as e:
        return {"motor": motor.ad, "hata": str(e)}


def sor(govde):
    """Tek soruyu seçili motorlara paralel sorar."""
    durum = (govde.get("durum") or "").strip()
    talimat = (govde.get("talimat") or "").strip()
    ham = govde.get("secenekler") or {}
    secenekler = {k.strip(): (v or "").strip() for k, v in ham.items() if k.strip()}

    if not talimat:
        return 400, {"hata": "Soru metni boş olamaz."}
    if len(secenekler) < 2:
        return 400, {"hata": "En az 2 şık gerekli."}
    if not durum:
        # Jev'in state'i zorunlu; şıklar bağlamı taşımıyorsa soru metni state olur.
        durum = talimat

    secili = [m for m in (govde.get("motorlar") or list(MOTORLAR)) if m in MOTORLAR]
    if not secili:
        return 400, {"hata": "Çalışan motor yok. Açılış notlarına bak."}

    with ThreadPoolExecutor(max_workers=len(secili)) as havuz:
        isler = {m: havuz.submit(_tek_motor, MOTORLAR[m], durum, talimat, secenekler)
                 for m in secili}
        kararlar = {m: f.result() for m, f in isler.items()}

    return 200, {
        "durum": durum,
        "talimat": talimat,
        "secenekler": secenekler,
        "beklenen": govde.get("beklenen") or None,
        "kararlar": kararlar,
    }


def tum_seti_kos(govde):
    """19 sorunun tamamını seçili motorlarda koşturup raporlar.

    Sorular sırayla, motorlar paralel gider: aynı soruyu tüm motorlar aynı anda
    görür, ama bir sonraki soruya geçilmeden önce hepsi biter. Böylece gecikme
    ölçümü sıraya girmiş isteklerden etkilenmez.
    """
    kol = govde.get("kol") or "tr-q"
    if kol not in ("tr-q", "en-q"):
        return 400, {"hata": "Bilinmeyen kol: %r" % kol}

    secili = [m for m in (govde.get("motorlar") or list(MOTORLAR)) if m in MOTORLAR]
    if not secili:
        return 400, {"hata": "Çalışan motor yok."}

    motor_sonuclari = {m: [] for m in secili}
    hatalar = []
    t0 = time.perf_counter()

    with ThreadPoolExecutor(max_workers=len(secili)) as havuz:
        for soru in VERI:
            isler = {
                m: havuz.submit(MOTORLAR[m].karar, soru.durum,
                                soru.talimat(kol), soru.secenekler)
                for m in secili
            }
            for m, f in isler.items():
                try:
                    motor_sonuclari[m].append(rapor.Sonuc(soru, f.result(), kol))
                except MotorHatasi as e:
                    hatalar.append({"motor": m, "soru_id": soru.id, "hata": str(e)})

    bos = [m for m, ss in motor_sonuclari.items() if not ss]
    for m in bos:
        del motor_sonuclari[m]
    if not motor_sonuclari:
        return 502, {"hata": "Hiçbir soru cevaplanamadı.", "hatalar": hatalar}

    r = rapor.tam_rapor(motor_sonuclari)
    r["kol"] = kol
    r["sure_sn"] = round(time.perf_counter() - t0, 1)
    r["hatalar"] = hatalar
    r["satirlar"] = [s.as_dict() for ss in motor_sonuclari.values() for s in ss]
    return 200, r


def acilis():
    return {
        "motorlar": [
            {"ad": m, "etiket": {"jev": "Jev (typesafe.ai)",
                                 "spark": "Spark / Qwen",
                                 "gemma": "Spark / Gemma"}.get(m, m),
             "model": getattr(MOTORLAR[m], "model", "")}
            for m in MOTORLAR
        ],
        "notlar": ACILIS_NOTU,
        "kaynak": VERI.kaynak,
        "veri_notu": VERI.not_,
        "kapsam_disi": VERI.kapsam_disi,
        "sorular": [s.as_dict() for s in VERI],
    }


class Sunucu(BaseHTTPRequestHandler):
    server_version = "SystemOneKarsilastir/1.0"

    def _yolla(self, kod, govde, tip):
        self.send_response(kod)
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def _json(self, kod, veri):
        self._yolla(kod, json.dumps(veri, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8")

    def _govde(self):
        uzunluk = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(uzunluk) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(ARAYUZ, "rb") as f:
                self._yolla(200, f.read(), "text/html; charset=utf-8")
        elif self.path == "/api/acilis":
            self._json(200, acilis())
        else:
            self._json(404, {"hata": "bulunamadı"})

    def do_HEAD(self):
        """Sağlık yoklamaları HEAD atıyor; gövdesiz 200/404 dön, 501 değil."""
        var = self.path in ("/", "/index.html", "/api/acilis")
        self.send_response(200 if var else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        islem = {"/api/sor": sor, "/api/kos": tum_seti_kos}.get(self.path)
        if islem is None:
            self._json(404, {"hata": "bulunamadı"})
            return
        try:
            govde = self._govde()
        except (ValueError, json.JSONDecodeError) as e:
            self._json(400, {"hata": "Gövde okunamadı: %s" % e})
            return
        kod, cevap = islem(govde)
        self._json(kod, cevap)

    def log_message(self, bicim, *args):
        """Varsayılan erişim günlüğü gürültülü; yalnız hataları göster."""
        try:
            kod = int(args[1])
        except (IndexError, ValueError):
            kod = 0
        if 200 <= kod < 400:
            return
        sys.stderr.write("  %s %s\n" % (self.address_string(), bicim % args))


def main():
    global VERI, MOTORLAR

    ap = argparse.ArgumentParser(description="Jev / Spark karşılaştırma arayüzü")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--adres", default="127.0.0.1")
    ap.add_argument("--motor", action="append", choices=["jev", "spark", "gemma"],
                    help="yalnız bu motor(lar); tekrarlanabilir. Varsayılan: hepsi")
    args = ap.parse_args()

    for akis in (sys.stdout, sys.stderr):
        if akis.encoding and akis.encoding.lower() != "utf-8":
            try:
                akis.reconfigure(encoding="utf-8")
            except Exception:
                pass

    VERI = veriseti.yukle()
    MOTORLAR = motorlari_kur(load_config(), args.motor or ["jev", "spark", "gemma"])

    print("%d soru yüklendi (%s)" % (len(VERI), VERI.kaynak))
    for ad, m in MOTORLAR.items():
        print("  %-6s %r" % (ad, m))
    for n in ACILIS_NOTU:
        print("  ! %s" % n)
    if not MOTORLAR:
        print("\nHiçbir motor kurulamadı. Anahtarları .env'e ekleyip tekrar dene.")
        return 2

    print("\nhttp://%s:%d\n" % (args.adres, args.port))
    sunucu = ThreadingHTTPServer((args.adres, args.port), Sunucu)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatılıyor")
    finally:
        sunucu.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
