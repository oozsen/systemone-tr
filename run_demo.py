"""Duman testi: yöntemin bu makinede çalıştığını gösterir.

    python run_demo.py                      # .env'deki ayarlarla, LiteLLM üzerinden
    python run_demo.py --docker             # sunucunun üstünde, doğrudan vLLM'e
    python run_demo.py --state "..."        # tek bir metni sınıflandır
    python run_demo.py --raw                # ham top_logprobs listesini de bas

Anahtar `.env` dosyasından okunur (bkz. .env.example). Bu betik BİR DOĞRULUK ÖLÇÜMÜ
DEĞİLDİR -- beş vaka yöntemin ayakta olduğunu söyler, modelin ne kadar iyi olduğunu
değil.
"""
import argparse
import json
import sys

from systemone import (
    DockerTransport,
    LiteLLMTransport,
    ScoringError,
    SMOKE_CASES,
    TransportError,
    load_config,
    questions,
    score,
)


def use_utf8():
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def main():
    use_utf8()
    cfg = load_config()

    ap = argparse.ArgumentParser(description="systemone-tr duman testi")
    ap.add_argument("--base-url", default=cfg["base_url"])
    ap.add_argument("--api-key", default=cfg["api_key"])
    ap.add_argument("--model", default=cfg["model"])
    ap.add_argument("--docker", action="store_true",
                    help="sunucunun üstünde: LiteLLM'i atla, doğrudan vLLM konteynerine")
    ap.add_argument("--container", default=cfg["container"])
    ap.add_argument("--state", help="sınama setini atla, tek metni sınıflandır")
    ap.add_argument("--raw", action="store_true", help="ham top_logprobs listesini bas")
    ap.add_argument("--timeout", type=float, default=120.0)
    args = ap.parse_args()

    if args.docker:
        transport = DockerTransport(args.container, timeout=args.timeout)
    else:
        if not args.api_key:
            print("Anahtar yok. `.env` dosyası oluştur (.env.example'ı kopyala) ve\n"
                  "SYSTEMONE_API_KEY satırını doldur. Aranan yol: %s" % cfg["env_path"],
                  file=sys.stderr)
            return 2
        transport = LiteLLMTransport(args.base_url, args.api_key, timeout=args.timeout)

    question = questions.departman()
    print("model=%s  taşıyıcı=%r" % (args.model, transport))
    if not args.docker:
        print(".env: %s" % ("bulundu" if cfg["env_found"] else "YOK (ortam değişkeni kullanıldı)"))
    print()

    try:
        if args.state:
            d = score(transport, args.model, args.state, question)
            print("  %-12s guven=%.3f  (%.0f ms)" % (d.label, d.confidence, d.latency_ms))
            print("  olasiliklar:", json.dumps(d.probabilities, ensure_ascii=False))
            if d.missing:
                print("  not: top-20'de yok:", ", ".join(d.missing))
            return 0

        print("ısınma...", flush=True)
        score(transport, args.model, SMOKE_CASES[0][1], question)

        hits = 0
        for expected, text in SMOKE_CASES:
            d, raw = score(transport, args.model, text, question, return_raw=True)
            ok = d.label == expected
            hits += ok
            print("  %s beklenen=%-11s bulunan=%-11s guven=%.3f  (%.0f ms)"
                  % ("OK  " if ok else "MISS", expected, d.label, d.confidence, d.latency_ms))
            print("       ", json.dumps(d.probabilities, ensure_ascii=False))
            if d.missing:
                print("        not: top-20'de yok:", ", ".join(d.missing))
            if args.raw:
                for e in raw[:20]:
                    print("          %-12r %8.4f" % (e.get("token"), e.get("logprob", float("-inf"))))

        print("\n%d/%d isabet" % (hits, len(SMOKE_CASES)))
        print("Bu bir doğruluk ölçümü değildir -- yöntemin çalıştığının kanıtıdır.")
        return 0
    except (TransportError, ScoringError) as e:
        print("\nHATA: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
