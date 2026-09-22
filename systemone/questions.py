"""Tipli sorular ve Türkçe hazır setler.

Şimdilik yalnız `choice` var: tek forward pass'te harf logit'i okuma yöntemi doğrudan
buna oturuyor. `score` (sıralı seviye) ve `noul` (ikili) aynı okumanın üstüne kurulur
ama ayrı doğrulama ister -- ölçülmeden eklenmeyecek.
"""


class Choice:
    """Seçenekli karar sorusu.

    options: [(etiket, açıklama), ...] -- sıra harflere (A, B, C...) karşılık gelir,
    dolayısıyla sıra değişirse prompt da değişir. Ölçüm yaparken sabit tut.
    """

    def __init__(self, prompt, options):
        if not options:
            raise ValueError("en az bir seçenek gerekir")
        labels = [label for label, _ in options]
        if len(set(labels)) != len(labels):
            raise ValueError("seçenek etiketleri benzersiz olmalı: %r" % (labels,))
        self.prompt = prompt
        self.options = list(options)

    def __repr__(self):
        return "Choice(%r, %d seçenek)" % (self.prompt, len(self.options))

    @property
    def labels(self):
        return [label for label, _ in self.options]


def departman():
    """Destek talebi yönlendirmesi. turkce_kurulum.py'daki soruyla aynı kategoriler."""
    return Choice(
        "Bu destek talebi hangi departmanı ilgilendirir?",
        [
            ("faturalama", "faturalar, ödemeler, iadeler"),
            ("teknik", "hatalar, kesintiler, sistem sorunları"),
            ("satış", "fiyatlandırma, yeni sözleşmeler"),
            ("diğer", "diğer her şey"),
        ],
    )


def aciliyet():
    """Sıralı aciliyet -- `choice` olarak modellendi (score primitifi henüz yok)."""
    return Choice(
        "Bu talebin aciliyeti ne kadar?",
        [
            ("düşük", "acil değil, beklemeye tahammülü var"),
            ("orta", "yakın zamanda ilgilenilmeli"),
            ("yüksek", "kritik son tarih veya engelleyici sorun"),
        ],
    )


# Yöntemin çalıştığını göstermek için kullanılan vakalar. BİR DOĞRULUK ÖLÇÜMÜ DEĞİLDİR:
# dört kategori semantik olarak birbirinden uzak, gerçek talepler böyle temiz gelmez.
SMOKE_CASES = [
    ("faturalama", "Merhaba, Mart ayı için iki kez ücret tahsil edildi. Lütfen bugün fazla "
                   "tahsil edilen tutarı iade edin yoksa üyeliğimizi iptal edeceğiz."),
    ("teknik", "Uygulama her açılışta çöküyor, sürekli hata mesajı alıyorum."),
    ("satış", "Yeni fiyat listenizi öğrenebilir miyim? Ekibimizi büyütmek istiyoruz."),
    ("diğer", "Mesai saatleriniz ne zaman? Ofisiniz nerede bulunuyor?"),
    # Diakritiksiz yazım: Laya'nın dil tespitini yanıltan durum.
    ("teknik", "Sisteme giris yapamiyorum, sifremi sifirladim ama yine olmadi."),
]
