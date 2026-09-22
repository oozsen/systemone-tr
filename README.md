# systemone-tr

Mevcut vLLM'den **tipli karar okuması** — Türkçe odaklı, sisteme dokunmadan.

Model cevabı yazmaz; biz yazmadan önce seçeneklerin logit'lerini okuruz. Jev / SemIf'in
"direct typed logits" deseni, DGX Spark'ta zaten servis edilen Qwen3.8-27B üzerine.

```python
from systemone import LiteLLMTransport, questions, score

t = LiteLLMTransport("http://10.10.104.33:4000/v1", api_key="sk-...")
d = score(t, "qwen3.8-27b", "Faturamda iki kez ücret alınmış.", questions.departman())
d.label          # 'faturalama'
d.confidence     # 0.993
d.probabilities  # {'faturalama': 0.9990, 'teknik': 0.0005, ...}
```

## Kurulum

Bağımlılık yok — yalnız Python 3.10+. Anahtarı `.env`'e koy:

```bash
cp .env.example .env     # sonra SYSTEMONE_API_KEY satırını doldur
python run_demo.py
```

Sunucunun üstünden LiteLLM'i atlayarak (anahtar gerekmez):

```bash
python run_demo.py --docker
```

## Karşılaştırmalı arayüz

Aynı Türkçe benchmark sorusunu iki motora birden sorar ve iki dağılımı yan yana
gösterir: **Jev** (typesafe.ai — tipli cevabı API döndürür) ve **Spark** (DGX
Spark'taki vLLM — cevap yazılmadan logit okunur).

```bash
cp .env.example .env     # SYSTEMONE_API_KEY + TYPESAFE_API_KEY doldur
python web/sunucu.py     # http://127.0.0.1:8100
```

Anahtarlardan biri yoksa o motor devre dışı kalır, sayfa yine açılır
(`--motor spark` ile baştan tek kol da seçilebilir).

İki görünüm var: **tek soru** (iki dağılım aynı satırlarda hizalı) ve **tüm set**
(19 sorunun tamamı; doğruluk, kalibrasyon, gecikme ve motorların ayrıştığı sorular).
Aynı raporu terminalden almak için `python -m karsilastir.kosu`.

Veri seti `jev-test/benchmark/veriseti.py`'den dondurulmuştur
(`veri/benchmark_tr.json`, üreteci `araclar/veriseti_aktar.py`). Kaynak değişirse
betik yeniden koşulur ve diff'te ne değiştiği görünür.

### Ölçülenler (22.09.2026, kol tr-q)

19 soru, Jev `jev-1.13.0` ve Qwen3.8-27B-FP8:

| | Jev | Spark |
|---|---|---|
| Doğruluk | 16/19 (%84,2) | 17/19 (%89,5) |
| Gecikme (medyan) | 747 ms | 218 ms |
| Ücret | ~$0,0004 (token'dan hesaplandı) | ölçülmüyor |
| Güven farkı (doğrularda − yanlışlarda) | +0,481 | +0,701 |

Art arda iki koşumda doğruluk aynı çıktı (16/19 ve 17/19); gecikme ve güven farkı
son hanede oynadı (Jev +0,481 / +0,474). Sayılar tek koşumdan, sabit değil.

Fark ne kadar büyükse güven eşiği o kadar işe yarar. **İkisinde de eşikleme
çalışıyor:** her iki motorda da `güven ≥ 0.90` kovasında hata yok (Jev 9/9,
Spark 10/10), hatalar `< 0.70` kovasında toplanıyor.

İki uyarı:

* **İki güven sayısı aynı şeyi ölçmez.** Jev'inki kendi tanımı, bizimki
  `1 − H(p)/log k`. Aynı eksende çizilirler ama "Jev'in güveni daha yüksek" gibi
  bir cümle kurulamaz. Karşılaştırılabilir olan, her birinin KENDİ içinde doğruyu
  yanlıştan ayırma gücü.
* **19 soru bir ölçüm değildir.** Held-out bölünmüş değil, 12 soru açık uçludan
  çoktan seçmeliye dönüştürülmüş (ölçülen şey "üretebiliyor mu" değil "ayırt
  edebiliyor mu"), ve Spark'ın güveni çift tepeli: `0.70–0.90` kovasında hiç vaka
  yok. Bu tam da şüphelenilmesi gereken şekil.

## Yöntem

1. Seçenekler `A/B/C...` harflerine eşlenir, modele "yalnız tek harf yaz" denir.
2. `max_tokens=1` ile tek pozisyon çalıştırılır.
3. O pozisyonun `top_logprobs`'undan seçenek harfleri süzülür.
4. Yalnız o küme üzerinde yeniden normalize edilir.

**Sunucuda hiçbir ayar değişmiyor.** Sebebi: vLLM'de `--logprobs-mode` varsayılanı
`raw_logprobs` (değerler "temperature=1.0 gibi" döner, istekteki temperature'dan
etkilenmez) ve `--max-logprobs` varsayılanı 20 (4-6 seçenek için fazlasıyla yeterli).

Güven skoru `1 - H(p)/log k` — Laya'nın `confidence_from_probs` fonksiyonuyla birebir
aynı formül, böylece iki yaklaşımın sayıları karşılaştırılabilir kalır.

`k` **her zaman seçenek sayısıdır**, top-20'de kaç harf bulunduğu değil. Pencereye
giremeyen seçeneğe pencerenin kesim değeri atanır (bir üst sınır: top-20'ye
giremediyse olasılığı en fazla 20'incininki kadardır) ve `Decision.missing`
alanında raporlanır. Bulunanlar üzerinden normalize etmek güveni sahte biçimde
yükseltirdi — iki seçenek kaybolduğunda entropi `log 2` ile bölünür, tek seçenek
kalırsa güven `1.0`'a fırlardı.

## Ölçülenler — `departman` duman testi (22.09.2026)

Qwen3.8-27B-FP8, LiteLLM üzerinden LAN'dan, 4 seçenekli `departman` sorusu.
Bu yalnız yöntemin ayakta olduğunu gösterir; asıl benchmark sayıları yukarıdaki
"Karşılaştırmalı arayüz" bölümünde:

| | |
|---|---|
| Duman testi | 5/5 |
| Gecikme | ~210 ms/karar (ağ + LiteLLM sıçraması dahil) |
| Güvenler | 0.980 – 0.993 |
| Diakritiksiz Türkçe | doğru bildi, güven anlamlı şekilde düştü (0.898) |

Referans: laya reposunun tablosunda Jev 710 ms/vaka.

## Ölçülmeyenler

Bunlar bilinmiyor, tahmin edilmemeli:

* **Harf yanlılığı.** Seçenekler `A/B/C...` harflerine SIRAYLA eşlendiği için şık
  sırası prompt'u değiştirir ve cevabı da değiştirebilir. Jev'de bu sorun yok:
  şıklar adlarıyla gider. `SparkMotoru.karar(..., ters=True)` aynı soruyu ters
  sırayla sorar ama **henüz koşturulmadı.** Doğruluk sayıları bu ölçülmeden tam
  olarak okunamaz — 19 sorunun kaçı içerik, kaçı konum yüzünden doğru bilinmiyor.
* **Gerçek doğruluk.** 19 soru bir ölçüm değildir: held-out bölünmüş değil, 12'si
  açık uçludan çoktan seçmeliye dönüştürülmüş, ve iki kategori tek soruyla temsil
  ediliyor. Kapsam dışı bırakılanlar `veri/benchmark_tr.json` içinde listeli.
* **ECE.** Kalibrasyon şu an kaba kovalarla bakılıyor (`≥0.90 / 0.70–0.90 / <0.70`).
  Tek sayıya indirmek (ECE) daha büyük bir set ister.
* **Gemma-4.** `--model gemma4-26b` ile çalışması beklenir ama denenmedi; NVFP4
  kuantizasyonu olasılıkları etkileyebilir, düşünme modunun nasıl kapatıldığı da belirsiz.
* **`score` / `noul` primitifleri.** Aynı okumanın üstüne kurulur ama ayrı doğrulama
  ister; ölçülmeden eklenmeyecek. Bu yüzden kaynak veri setindeki 2 noul seti
  aktarılmadı — karşılaştırılacak ikinci taraf yok.

Kalibrasyon artık tamamen bilinmeyen değil: 19 soruluk sette her iki motorda da
`güven ≥ 0.90` kovasında hata çıkmadı ve hatalar `< 0.70`'te toplandı. Bu, eşiklemenin
çalıştığına dair ilk kanıt — ama 19 soruluk bir kanıt.

## Sıradaki iş

1. **Harf yanlılığını ölç.** En ucuz ve en çok şeyi değiştirebilecek kontrol:
   aynı seti `ters=True` ile koştur, iki okumanın ayrıştığı soruları say.
2. **Seti büyüt.** Belirsiz ve sınırda vakalar, held-out bölünmüş. Sonra gerçek
   doğruluk ve ECE çıkar. Üretimi Spark'taki Qwen yapabilir; veri makineden çıkmaz.

## Yapı

```
systemone/        tipli karar okuması (transport / scorer / questions / config)
karsilastir/      iki motor tek arayüz: motor.py, rapor.py, veriseti.py, kosu.py
web/              sunucu.py + arayuz.html — yan yana karşılaştırma
veri/             benchmark_tr.json (dondurulmuş veri seti)
araclar/          veriseti_aktar.py — veri setini jev-test'ten yeniden üretir
run_demo.py       departman duman testi
```

## Bağlam

* [TheoLeeCJ/SemIf](https://github.com/TheoLeeCJ/SemIf) — yöntemin kaynağı (MIT)
* `jev-test` (private) — Jev tarafının referansı ve Türkçe benchmark'ın kaynağı.
  `veri/benchmark_tr.json` oradaki `benchmark/veriseti.py`'den dondurulmuştur;
  `karsilastir/motor.py`'deki Jev gövdesi oradaki `jev.py` ile birebir aynıdır
  (tek fark: `requests` yerine stdlib `urllib`).
* [vLLM engine args](https://docs.vllm.ai/en/stable/configuration/engine_args/) — `logprobs-mode`, `max-logprobs`
* Laya (`../laya`) — alternatif yaklaşım: eğitilmiş 322M encoder. Türkçede 20 seçenekli
  MASSIVE'de 0.370 / ECE 0.417. Bu proje onun yerine geçmiyor; karşılaştırma için duruyor.
