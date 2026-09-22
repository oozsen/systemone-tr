"""vLLM'e ulaşmanın iki yolu. Karar okuması taşıyıcıdan bağımsızdır.

LiteLLM yolu LAN'dan çalışır ve sanal anahtar ister; docker yolu yalnız sunucunun
üstünde çalışır ama ara katman ve auth olmadan doğrudan vLLM'e gider. İkisi de aynı
gövdeyi gönderir, dolayısıyla bir yolda görülen davranış diğerinde de geçerlidir --
tek fark, LiteLLM'in bilinmeyen alanları geçirip geçirmediğidir (ölçüldü: geçiriyor).
"""
import json
import subprocess
import urllib.error
import urllib.request


class TransportError(RuntimeError):
    """Taşıma katmanı hatası: bağlantı, auth, ya da bozuk yanıt."""


class LiteLLMTransport:
    """LiteLLM ağ geçidi üzerinden (LAN'dan erişilebilir, sanal anahtar ister)."""

    def __init__(self, base_url, api_key=None, timeout=120.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def __repr__(self):
        return "LiteLLMTransport(%s)" % self.base_url

    def complete(self, body):
        url = self.base_url + "/chat/completions"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            hint = ""
            if e.code == 401:
                hint = "\nAnahtar eksik ya da geçersiz (--api-key / SEMIF_API_KEY)."
            elif e.code == 400:
                hint = ("\nLiteLLM bir alanı geçirmiyor olabilir; DockerTransport ile "
                        "doğrudan vLLM'e giderek ayırt edebilirsin.")
            raise TransportError("HTTP %d %s\n%s%s" % (e.code, e.reason, detail, hint))
        except urllib.error.URLError as e:
            raise TransportError("Bağlanamadı: %s (%s erişilebilir mi?)" % (e.reason, self.base_url))


class DockerTransport:
    """`docker exec` ile doğrudan vLLM konteynerine -- LiteLLM ve auth devre dışı.

    vLLM 8000'i yalnızca `expose` eder, host'a publish etmez; bu yüzden sunucunun
    üstünden bile en kısa yol konteynerin içinden curl'lemektir.
    """

    def __init__(self, container="vllm", timeout=120.0):
        self.container = container
        self.timeout = timeout

    def __repr__(self):
        return "DockerTransport(%s)" % self.container

    def complete(self, body):
        cmd = [
            "docker", "exec", "-i", self.container,
            "curl", "-s", "-X", "POST", "http://localhost:8000/v1/chat/completions",
            "-H", "Content-Type: application/json", "-d", "@-",
        ]
        try:
            p = subprocess.run(cmd, input=json.dumps(body).encode("utf-8"),
                               capture_output=True, timeout=self.timeout)
        except FileNotFoundError:
            raise TransportError("`docker` bulunamadı -- bu yol yalnız sunucunun üstünde çalışır.")
        except subprocess.TimeoutExpired:
            raise TransportError("docker exec zaman aşımına uğradı (%.0fs)" % self.timeout)
        if p.returncode != 0:
            raise TransportError("docker exec başarısız (%d): %s"
                                 % (p.returncode, p.stderr.decode("utf-8", "replace")[:500]))
        try:
            return json.loads(p.stdout.decode("utf-8"))
        except json.JSONDecodeError:
            raise TransportError("vLLM'den JSON gelmedi:\n"
                                 + p.stdout.decode("utf-8", "replace")[:500])
