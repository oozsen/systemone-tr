"""Jev ile Spark'ı aynı Türkçe benchmark üzerinde yan yana koşturur.

    from karsilastir import JevMotoru, SparkMotoru, veriseti

    vs = veriseti.yukle()
    j = JevMotoru(api_key="...")
    s = SparkMotoru("http://10.10.104.33:4000/v1", "sk-...", "qwen3.8-27b")

    soru = vs.bul("tr_kavram")
    for m in (j, s):
        print(m.karar(soru.durum, soru.talimat_tr, soru.secenekler))

Web arayüzü: `python web/sunucu.py`. Toplu koşum: `python -m karsilastir.kosu`.
"""
from .motor import JevMotoru, Karar, MotorHatasi, SparkMotoru
from . import veriseti

__all__ = ["JevMotoru", "Karar", "MotorHatasi", "SparkMotoru", "veriseti"]
