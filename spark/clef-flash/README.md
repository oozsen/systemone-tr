# clef-flash (isteğe bağlı konteyner)

Cloudflare/clef-flash, 9B, BF16. Yüklüyken ~20 GiB birleşik bellek tutar.
**Sürekli açık değil.** Kullanırken başlat, bitince durdur.

    ~/clef-flash/baslat.sh       # bekçiyle başlatır; docker logs -f clef-flash
    docker stop clef-flash

**LlamaFactory ile eğitim başlatmadan önce `docker ps`'e bak; clef-flash açıksa durdur.**
Swap yok ve `--memory 28g` GPU ayırmalarını SAYMIYOR (GB10 birleşik bellek): taşma
global OOM olur. Bu yüzden `docker start` yerine `baslat.sh` kullan -- bekçi boş bellek
6 GiB altına düşerse clef-flash'ı öldürür.

Uç nokta (Jev'in gövdesiyle aynı):

    curl -s localhost:8101/health
    curl -s localhost:8101/v1/systemone -H 'Content-Type: application/json' -d '{
      "model": "clef-flash", "state": "Ödeme sayfası hata veriyor, siparişler duruyor.",
      "questions": {"kesinti": {"type": "noul", "instructions": "Bir servis çalışmıyor mu?"}}}'

Yeniden kurulum:

    docker build -t clef-flash:local ~/clef-flash
    docker run --rm -e HF_HOME=/data/hf -v /data/hf:/data/hf --entrypoint python3 clef-flash:local \
      -c 'from huggingface_hub import snapshot_download as s; s("Cloudflare/clef-flash", revision="17f0b0ad64efb65d273590632833508766b2aae6")'
    docker create --name clef-flash --gpus all --memory 28g --memory-swap 28g \
      -p 8101:8101 -v /data/hf:/data/hf:ro clef-flash:local

**Ağ güvenliği (düzenleme notu, 02.10.2026):** `-p 8101:8101` portu tüm arayüzlere
(`0.0.0.0`) açar ve sarmalayıcıda kimlik doğrulama yok -- paylaşımlı bir ağda
konteyner açık kaldıkça ağdaki herkes çağırabilir. Önerilen düzen: loopback'e bağla,
istemciden SSH tüneliyle eriş. Port eşlemesi `docker create` anında sabitlendiği için
konteyneri yeniden yaratmak gerekir (imaj aynı kalır):

    docker rm clef-flash
    docker create --name clef-flash --gpus all --memory 28g --memory-swap 28g       -p 127.0.0.1:8101:8101 -v /data/hf:/data/hf:ro clef-flash:local
    # istemcide:  ssh -N -L 8101:localhost:8101 <spark>   →   CLEF_URL=http://127.0.0.1:8101

Bu yapılana kadar: kullanmadığın an `docker stop clef-flash`.
