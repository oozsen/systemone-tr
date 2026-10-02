"""clef-flash için ince HTTP sarmalayıcı.

Model, Jev'in /v1/systemone istek/yanıt gövdesini birebir uyguluyor
(joint_schema_model.systemone). Burada yalnızca onu HTTP'ye açıyoruz.

Konteyner isteğe bağlı çalışır: ~/clef-flash/baslat.sh / docker stop clef-flash.
Düz `docker start` bellek bekçisini (bekci.sh) başlatmaz.
Eğitim (llamafactory) başlamadan önce durdurulmalı -- yüklüyken ~20 GiB tutar.
"""

import os
import sys
import threading
import time

import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from huggingface_hub import snapshot_download

REPO = os.environ.get("CLEF_REPO", "Cloudflare/clef-flash")
REVISION = os.environ.get("CLEF_REVISION", "17f0b0ad64efb65d273590632833508766b2aae6")
PORT = int(os.environ.get("CLEF_PORT", "8101"))

path = snapshot_download(REPO, revision=REVISION, local_files_only=True)
sys.path.insert(0, path)
from joint_schema_model import ClefModel, JointSchemaHead, systemone  # noqa: E402


def yukle(path):
    """joint_schema_model.load_release_model'in birebir karşılığı, bir farkla.

    GB10'da CPU ve GPU aynı fiziksel belleği paylaşıyor. from_pretrained
    ağırlıkları önce CPU'da açıp GPU'ya kopyaladığı için yüklemede tepe ~2x
    model oluyor (02.10.2026: 35 GiB boşta global OOM). Burada model doğrudan
    GPU'da kurulur ve her tensör safetensors'tan tek tek GPU'ya okunup yerine
    kopyalanır: tepe ~ model + bir tensör.
    """
    import json
    from pathlib import Path

    from safetensors import safe_open
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoProcessor, Qwen3_5ForConditionalGeneration

    path = Path(path)
    config = AutoConfig.from_pretrained(path)
    with torch.device("cuda"):
        backbone = Qwen3_5ForConditionalGeneration._from_config(config, dtype=torch.bfloat16)
    params = dict(backbone.named_parameters())
    dosyalar = sorted(set(json.loads((path / "model.safetensors.index.json").read_text())
                          ["weight_map"].values()))
    yuklenen = set()
    with torch.no_grad():
        for dosya in dosyalar:
            with safe_open(str(path / dosya), framework="pt", device="cuda") as f:
                for anahtar in f.keys():
                    t = f.get_tensor(anahtar)
                    params[anahtar].copy_(t)
                    del t
                    yuklenen.add(anahtar)
    eksik = set(params) - yuklenen
    if eksik:
        raise RuntimeError("yüklenmeyen ağırlıklar: %s" % sorted(eksik)[:5])
    backbone.config.use_cache = False

    head = JointSchemaHead(**json.loads((path / "joint_head_config.json").read_text()))
    head.load_state_dict(load_file(path / "joint_head.safetensors"), strict=True)
    head = head.to(device="cuda", dtype=torch.bfloat16)
    processor = AutoProcessor.from_pretrained(path)
    torch.cuda.empty_cache()
    return ClefModel(backbone, head).eval(), processor


t0 = time.perf_counter()
model, processor = yukle(path)
print("model yüklendi: %.1f s, revizyon %s" % (time.perf_counter() - t0, REVISION[:12]), flush=True)

# Tek GPU, tek model: istekler sırayla koşar.
kilit = threading.Lock()
app = FastAPI(title="clef-flash")


@app.get("/health")
def health():
    return {"status": "ok", "model": REPO, "revision": REVISION}


@app.post("/v1/systemone")
def v1_systemone(istek: dict):
    if istek.get("images") or istek.get("videos"):
        raise HTTPException(400, "görsel/video bu sarmalayıcıda henüz desteklenmiyor")
    try:
        with kilit:
            return systemone(model, processor, istek)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except torch.cuda.OutOfMemoryError:
        torch.cuda.empty_cache()
        raise HTTPException(503, "GPU belleği yetmedi")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
