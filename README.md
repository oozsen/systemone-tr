# systemone-tr

Mevcut vLLM'den **tipli karar okuması** — Türkçe odaklı, sisteme dokunmadan.

Model cevabı yazmaz; biz yazmadan önce seçeneklerin logit'lerini okuruz. Jev /
SemIf'in "direct typed logits" deseni, DGX Spark'ta zaten servis edilen
Qwen3.8-27B ve Gemma4-26B üzerine. Veri makineden çıkmaz, karar başına ek ücret
yoktur, sunucuda tek bir ayar değişmez.

```python
from systemone import LiteLLMTransport, questions, score

t = LiteLLMTransport("http://10.10.104.33:4000/v1", api_key="sk-...")
d = score(t, "qwen3.8-27b", "Faturamda iki kez ücret alınmış.", questions.departman())
d.label          # 'faturalama'
d.confidence     # 0.993
d.probabilities  # {'faturalama': 0.9990, 'teknik': 0.0005, ...}
```

## Neden yerel

Sınıflandırıcının karar verebilmesi için **veriyi görmesi gerekir.** "Bu metin
gizli mi?", "Kişisel veri içeriyor mu?", "Bu talep hukuka mı gitmeli?" —
bunların hepsi metne bakmadan cevaplanamaz.

Sınıflandırıcı bir bulut API'siyse, cevap size dönmeden önce veri ağınızdan
çıkmıştır. **"Bu veri gizli mi?" diye sormak için bile veriyi dışarı vermiş
olursunuz.** Cevap "evet, gizli" gelse ne fark eder — iş işten geçmiştir. Yani
kararın en çok önem taşıdığı yerde, tam da orada, bulut sınıflandırıcı kendi
amacını baltalar.

Bunun için açık ağırlıklı bir Jev sürümü beklemeye gerek yok. **Mekanizma
modele özel değil.** Zaten servis ettiğiniz herhangi bir modele `max_tokens=1`
ve `logprobs` göndermek yeterli; sunucuda tek bir ayar değiştirmeden, veriyi
makineden çıkarmadan, karar başına ek ücret ödemeden çalışır. Bu depo bunu
DGX Spark'taki Qwen3.8-27B ve Gemma4-26B üzerinde gösteriyor.

**Ama "yerel" otomatik olarak "aynı derecede iyi" demek değil.** Jev tipli ve
kalibre kararlar için eğitilmiş; genel bir sohbet modeli değil. Kendi
ölçümümüzde fark modele göre ciddi biçimde değişiyor: Qwen'in güveni doğruyu
yanlıştan iyi ayırıyor, Gemma'nınki neredeyse hiç ayırmıyor (aşağıdaki tablo).
Kazandığınız şey gizlilik ve marjinal maliyetin sıfırlanması; ödediğiniz bedel,
kalibrasyonu kendi modelinizde **kendinizin ölçmek zorunda olması.** Bu depodaki
düzeneğin asıl işi de bu ölçümü yapmak.

Ücret konusunda dürüst olalım: karar başına marjinal maliyet yok, ama donanım ve
elektrik gerçek. Tablolarda "bedava" değil **"ölçülmüyor"** yazmasının sebebi bu.

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

Aynı Türkçe benchmark sorusunu üç motora birden sorar ve dağılımları yan yana
gösterir:

| kol | nedir | nasıl okunur |
|---|---|---|
| `jev` | typesafe.ai System One | tipli cevabı API döndürür |
| `spark` | DGX Spark / Qwen3.8-27B-FP8 | cevap yazılmadan logit okunur |
| `gemma` | DGX Spark / Gemma4-26B | cevap yazılmadan logit okunur |

İki Spark kolu aynı LiteLLM ağ geçidini, farklı modelleri kullanır.

```bash
cp .env.example .env     # SYSTEMONE_API_KEY + TYPESAFE_API_KEY doldur
python web/sunucu.py     # http://127.0.0.1:8100
```

Anahtarı olmayan ya da servis edilmeyen kol devre dışı kalır, sayfa yine açılır.
`--motor spark --motor gemma` ile baştan alt küme de seçilebilir (Jev'e para
harcamadan koşmak için işe yarar).

İki görünüm var: **tek soru** (dağılımlar aynı satırlarda hizalı) ve **tüm set**
(setin tamamı; doğruluk, kalibrasyon, gecikme ve motorların ayrıştığı sorular).
Aynı raporu terminalden almak için `python -m karsilastir.kosu`.

### Soru seti

Depoda **`veri/demo_tr.json`** var: on soruluk, bu depo için sıfırdan yazılmış bir
demo seti. Düzeneğin ayakta olduğunu ve üç motorun yan yana okunabildiğini
gösterir — **doğruluk ölçmez.**

Kendi setinizi bağlamak için aynı şemada bir JSON yazıp gösterin:

```bash
SYSTEMONE_VERISETI=/yol/benim_setim.json python web/sunucu.py
```

Kendi benchmark'ınız başka biçimdeyse `araclar/veriseti_aktar.py` dönüştürme
betiğine örnektir. `veri/*.json` (demo hariç) bilinçli olarak gitignore'da:
telifi belirsiz ya da özel veri kazara commit edilmesin.

### Ölçülenler (22.09.2026, kol tr-q)

Aşağıdaki sayılar **paylaşılmayan özel bir 19 soruluk Türkçe sette** ölçüldü; o
set telif durumu netleşmediği için depoya girmiyor. Yani bu tablo bu repodan
birebir tekrarlanamaz — deponun demo seti on sorudur ve başka sorulardan oluşur.
Sayılar yöntemin ne ürettiğini gösterir, bir kıyas ilanı değildir.

Jev `jev-1.13.0`, Qwen3.8-27B-FP8, Gemma4-26B:

| | Jev | Qwen | Gemma |
|---|---|---|---|
| Doğruluk | 16/19 (%84,2) | **17/19 (%89,5)** | 16/19 (%84,2) |
| Gecikme (medyan) | 720 ms | 313 ms | **203 ms** |
| Ücret | ~$0,0004 (token'dan) | ölçülmüyor | ölçülmüyor |
| Güven farkı (doğrularda − yanlışlarda) | +0,410 | **+0,701** | +0,270 |
| Güveni ≥ 0,90 olan yargı | 9/19 (%47) | 10/19 (%53) | 17/19 (%89) |

Üç motor da aynı yerde zorlanıyor: Finans ve `mantik_otobus`. Ayrıştıkları tek
soru `finans_gelismis` — orada yalnız Qwen doğru bildi.

Sayılar tek koşumdan. Art arda koşumlarda **doğruluk değişmedi** (16/17/16), ama
gecikme ve güven farkı oynadı (Jev +0,410 / +0,475; Gemma +0,270 / +0,313; Gemma
gecikme 203 / 143 ms). Tablodaki kesin haneleri değil, büyüklük sırasını okuyun.

**En önemli satır sonuncusu.** Gemma doğrulukta Jev ile başa baş ve en hızlısı,
ama güveni tepede yığılıyor: 19 yargının 17'si `≥ 0,90` kovasında. Yani "emin
olduğunda çalıştır, olmadığında insana sor" tasarımı Gemma ile neredeyse hiçbir
şeyi elemez — eşik koysanız da her şey geçer. Qwen'de aynı kova 10/19, ve doğru/
yanlış güven farkı iki buçuk katı. **Gemma'yı seçmek hızı alıp triyajı bırakmaktır.**

Üç uyarı:

* **Güven sayıları aynı şeyi ölçmez.** Jev'inki kendi tanımı, Spark kollarınınki
  `1 − H(p)/log k`. Aynı eksende çizilirler ama "Jev'in güveni daha yüksek" gibi
  bir cümle kurulamaz. Karşılaştırılabilir olan, her motorun KENDİ içinde doğruyu
  yanlıştan ayırma gücü.
* **Gemma'da pencere darlığı gerçek bir sınır.** Dağılımı o kadar tepeli ki rakip
  şıklar sık sık `top-20` penceresine hiç girmiyor (bu sette 19 yargının 1'inde
  hiçbiri girmedi). O satırlarda güven ölçüm değil, pencerenin ürünüdür; arayüz
  ve CLI bunu ayrıca işaretler. Sunucudaki `--max-logprobs` varsayılanı 20 olduğu
  için pencere büyütülemiyor.
* **19 soru bir ölçüm değildir.** Held-out bölünmüş değil, 12 soru açık uçludan
  çoktan seçmeliye dönüştürülmüş, ve iki kategori tek soruyla temsil ediliyor.

## Yöntem

### Logit nedir, biz ne okuyoruz

Bir dil modeli her pozisyonda **kelime dağarcığındaki her token için bir sayı**
üretir. Bu ham sayılara *logit* denir; Qwen3 için pozisyon başına yüz binden
fazla logit demek. `softmax` bunları olasılığa çevirir:

```
p(token i) = exp(z_i) / Σ_j exp(z_j)
```

Normal üretimde bu dağılımdan bir token seçilir (örnekleme ya da en yükseği) ve
**geri kalan atılır.** Oysa asıl bilgi atılan kısımda: modelin o pozisyonda
neyi ne kadar olası gördüğü, yani kendi belirsizliği.

Tipli karar okuması bu bilgiyi kurtarır. Üç adım:

1. **Cevabı tek token'a indir.** Seçenekler `A/B/C...` harflerine eşlenir, modele
   "yalnızca tek bir harf yaz" denir. Böylece kararın tamamı tek bir pozisyona sığar.
2. **Tek pozisyon çalıştır.** `max_tokens=1`. Tek forward pass, sıfır üretilmiş
   cevap token'ı. Model cevabı yazmaz — biz yazmadan önce okuruz.
3. **O pozisyonun dağılımını oku ve daralt.** `logprobs` ile dönen listeden
   seçenek harfleri süzülür ve yalnız o küme üzerinde yeniden normalize edilir:

```
p(seçenek i) = exp(z_i) / Σ_{j ∈ seçenekler} exp(z_j)
```

Bu daraltma "cevap bu seçeneklerden biridir" koşuluna geçmek demektir; modelin
noktalama, boşluk ya da başka kelimelere ayırdığı olasılık kütlesi atılır.

**Neden bu sayı, modele "ne kadar eminsin" diye sormaktan iyi.** İkincisi
modelin belirsizlik hakkında *ürettiği metindir* — eğitim verisinde "%90
eminim" ifadesinin nasıl geçtiğini yansıtır, modelin gerçek iç durumunu değil.
Logit dağılımı ise doğrudan iç durumun kendisi. Ayrıca `temperature=0`'da
deterministiktir: aynı soruyu üç kez sorduk, altı ondalığa kadar aynı çıktı.
(Jev'inki değil — aynı soruda 0.76 ile 0.82 arasında oynadı.)

**Kurtarılan şey bir ihtimal, kesinlik değil.** Dağılımın tepeli olması modelin
haklı olduğunu göstermez, yalnız kararsız olmadığını gösterir. Bu ikisinin
birbirini ne kadar tuttuğu ölçülmesi gereken ayrı bir şeydir — kalibrasyon
tablosunun varlık sebebi bu. Demo setindeki `mantik_kalem` sorusu tam da bunu
gösteriyor: Gemma `1.00` güvenle yanlış cevap veriyor.

### Sunucuda hiçbir ayar değişmiyor

vLLM'de `--logprobs-mode` varsayılanı `raw_logprobs`: değerler "temperature=1.0
gibi" döner, istekteki temperature'dan etkilenmez. Dolayısıyla dağılım bozulmaz
ve `temperature=0` göndermek okumayı değiştirmez.

`--max-logprobs` varsayılanı ise 20 — ve buradaki incelik önemli: dönen liste
**tüm kelime dağarcığının** top-20'sidir, sizin seçenek kümenizin değil. Prompt
genelde harfleri tepeye taşır, ama model çok tepeliyse rakip harfler pencereye
hiç girmeyebilir. Gemma'da tam olarak bu oluyor. O durumda dağılım ölçülmüş
değil, pencere tarafından kırpılmıştır; kod bunu `missing` / `pencerede` ile
raporlar ve arayüz açıkça işaretler. Pencere büyütülemiyor: 20'den fazlası 400
döndürür.

Aynı gövde iki modelde de çalışıyor. Qwen3.8 düşünme modu açık geldiği için
`chat_template_kwargs={"enable_thinking": false}` gönderiliyor; **Gemma bu alanı
sessizce yok sayıyor** (varken de yokken de ilk token doğrudan harf geliyor,
ölçüldü), dolayısıyla gövdeyi modele göre dallandırmaya gerek yok.

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

Referans: Laya'nın kendi tablosunda Jev 710 ms/vaka.

## Ölçülmeyenler

Bunlar bilinmiyor, tahmin edilmemeli:

* **Harf yanlılığı.** Seçenekler `A/B/C...` harflerine SIRAYLA eşlendiği için şık
  sırası prompt'u değiştirir ve cevabı da değiştirebilir. Jev'de bu sorun yok:
  şıklar adlarıyla gider. `SparkMotoru.karar(..., ters=True)` aynı soruyu ters
  sırayla sorar ama **henüz koşturulmadı.** Doğruluk sayıları bu ölçülmeden tam
  olarak okunamaz — 19 sorunun kaçı içerik, kaçı konum yüzünden doğru bilinmiyor.
* **Gerçek doğruluk.** 19 soru bir ölçüm değildir: held-out bölünmüş değil, 12'si
  açık uçludan çoktan seçmeliye dönüştürülmüş, ve iki kategori tek soruyla temsil
  ediliyor. Bu set depoda yok (yukarıya bak).
* **ECE.** Kalibrasyon şu an kaba kovalarla bakılıyor (`≥0.90 / 0.70–0.90 / <0.70`).
  Tek sayıya indirmek (ECE) daha büyük bir set ister.
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
karsilastir/      motorlar tek arayüzde: motor.py, rapor.py, veriseti.py, kosu.py
web/              sunucu.py + arayuz.html — yan yana karşılaştırma
veri/             demo_tr.json — on soruluk demo seti (özgün, MIT)
araclar/          veriseti_aktar.py — kendi setini bu şemaya çeviren örnek betik
run_demo.py       departman duman testi
```

## Bağlam

* [TheoLeeCJ/SemIf](https://github.com/TheoLeeCJ/SemIf) — yöntemin kaynağı (MIT)
* [TypeSafe belgeleri](https://docs.typesafe.ai) — Jev'in istek/cevap sözleşmesi.
  `karsilastir/motor.py`'deki Jev gövdesi bu sözleşmeye göre yazıldı; tek fark
  resmî SDK yerine stdlib `urllib` kullanılması (bağımlılık eklememek için).
* [vLLM engine args](https://docs.vllm.ai/en/stable/configuration/engine_args/) — `logprobs-mode`, `max-logprobs`
* Laya — alternatif yaklaşım: eğitilmiş 322M encoder (bu depoda değil, özel).
  Türkçede 20 seçenekli MASSIVE'de 0.370 / ECE 0.417. Bu proje onun yerine
  geçmiyor; karşılaştırma için anılıyor.

## Lisans

MIT — `LICENSE`. `veri/demo_tr.json` dahil deponun tamamı aynı lisans altındadır.
