#!/bin/sh
# clef-flash bellek bekçisi. GB10'da `docker --memory` GPU ayırmalarını saymıyor;
# taşma global OOM olur ve killer vLLM'i de seçebilir. Boş bellek ESIK_MIB'in
# altına düşerse clef-flash'ı öldürür. Konteyner durunca kendisi de çıkar.
ESIK_MIB=${ESIK_MIB:-6144}
sleep 2
while [ "$(docker inspect -f '{{.State.Running}}' clef-flash 2>/dev/null)" = true ]; do
  bos=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
  if [ "$bos" -lt "$ESIK_MIB" ]; then
    docker kill clef-flash >/dev/null
    echo "$(date '+%F %T') boş bellek ${bos} MiB < ${ESIK_MIB} MiB: clef-flash öldürüldü"
    exit 1
  fi
  sleep 0.5
done
