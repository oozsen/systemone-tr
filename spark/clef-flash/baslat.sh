#!/bin/sh
# clef-flash'ı bekçisiyle başlatır. Durdurmak için: docker stop clef-flash
cd "$(dirname "$0")"
docker start clef-flash >/dev/null || exit 1
nohup ./bekci.sh >> bekci.log 2>&1 &
echo "clef-flash başladı, bekçi açık (bekci.log). Hazır olunca: curl -s localhost:8101/health"
