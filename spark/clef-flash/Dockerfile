# vLLM imajı zaten torch 2.11.0+cu130 (aarch64, GB10/sm_121) taşıyor; modelin
# istediği sürüm. Yalnızca transformers'ı yükseltiyoruz -- bu imajın içinde,
# çalışan vllm konteynerlerine dokunmadan.
FROM vllm/vllm-openai:cu130-nightly

RUN pip install --no-cache-dir "transformers==5.10.2" pillow

COPY server.py /app/server.py
ENV HF_HOME=/data/hf
ENTRYPOINT ["python3", "/app/server.py"]
