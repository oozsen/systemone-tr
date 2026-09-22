"""Ayar okuma: .env dosyası -> ortam değişkeni -> varsayılan.

Bağımlılık eklememek için python-dotenv kullanılmıyor; .env ayrıştırması burada,
stdlib ile. Desteklenen biçim `ANAHTAR=değer`, `#` ile yorum, isteğe bağlı tırnak
ve `export ` öneki.

Öncelik: açıkça verilen argüman > ortam değişkeni > .env > varsayılan.
Böylece CI'da ortam değişkeni, geliştirmede .env çalışır ve ikisi çakışmaz.
"""
import os

DEFAULTS = {
    "SYSTEMONE_BASE_URL": "http://10.10.104.33:4000/v1",
    "SYSTEMONE_MODEL": "qwen3.8-27b",
    "SYSTEMONE_CONTAINER": "vllm",
    # Aynı ağ geçidinde servis edilen ikinci model. Karşılaştırmanın üçüncü kolu.
    "SYSTEMONE_GEMMA_MODEL": "gemma4-26b",
    "JEV_MODEL": "jev-latest",
}


def parse_env_file(path):
    """.env -> dict. Dosya yoksa boş dict; bozuk satırlar sessizce atlanır."""
    values = {}
    if not os.path.exists(path):
        return values
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].lstrip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key:
                values[key] = value
    return values


def load(env_path=None):
    """Ayarları döndür. `.env` proje kökünde aranır."""
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    file_values = parse_env_file(env_path)

    def get(key, default=None):
        # Ortam değişkeni .env'i ezer: kabukta bilinçli olarak verilen kazanır.
        return os.environ.get(key) or file_values.get(key) or default

    return {
        "api_key": get("SYSTEMONE_API_KEY") or get("SEMIF_API_KEY") or get("LITELLM_API_KEY"),
        "base_url": get("SYSTEMONE_BASE_URL", DEFAULTS["SYSTEMONE_BASE_URL"]),
        "model": get("SYSTEMONE_MODEL", DEFAULTS["SYSTEMONE_MODEL"]),
        "container": get("SYSTEMONE_CONTAINER", DEFAULTS["SYSTEMONE_CONTAINER"]),
        "gemma_model": get("SYSTEMONE_GEMMA_MODEL", DEFAULTS["SYSTEMONE_GEMMA_MODEL"]),
        # Karşılaştırmanın Jev kolu. Yoksa None; çağıran taraf tek kolla devam eder.
        "typesafe_api_key": get("TYPESAFE_API_KEY"),
        "jev_model": get("JEV_MODEL", DEFAULTS["JEV_MODEL"]),
        "env_path": env_path,
        "env_found": bool(file_values),
    }
