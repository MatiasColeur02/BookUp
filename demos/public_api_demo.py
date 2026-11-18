"""Servidor de la demo del catálogo público (API Gateway, módulo terraform/modules/public-api).

Sirve `public-api.html` y reenvía sus llamadas al API Gateway desde acá, del lado del
servidor: así el navegador nunca habla directo con AWS y no hay CORS de por medio (el
API Gateway no define OPTIONS ni headers CORS, y para `curl` no hacen falta).

Solo biblioteca estándar. Uso, desde la raíz del repo:

    python demos/public_api_demo.py

La URL y la API key salen, en este orden, de:
  1. --api-url / --api-key
  2. BOOKUP_PUBLIC_API_URL / BOOKUP_PUBLIC_API_KEY
  3. `terraform output` en terraform/organization (public_api_url y public_api_keys[--consumer])
También se pueden cargar o cambiar en caliente desde el botón ⚙ de la página (POST /config).

Escucha solo en 127.0.0.1: la clave nunca sale de tu máquina hacia el navegador.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
HTML_FILE = HERE / "public-api.html"
DEFAULT_TF_DIR = HERE.parent / "terraform" / "organization"

# Solo los 5 GET que expone el API Gateway. Cualquier otro path no se reenvía.
ALLOWED_PATH = re.compile(r"^books(/search|/cities|/[0-9Xx-]{1,20}(/availability)?)?$")

# Headers de la respuesta que vale la pena mostrar: los que agrega API Gateway y los del backend.
SHOWN_HEADERS = (
    "content-type",
    "x-amzn-requestid",
    "x-amz-apigw-id",
    "x-amzn-errortype",
    "x-amzn-trace-id",
    "x-cache",
    "retry-after",
)


def terraform_output(tf_dir: Path, name: str, as_json: bool = False) -> str | None:
    flag = "-json" if as_json else "-raw"
    try:
        result = subprocess.run(
            ["terraform", f"-chdir={tf_dir}", "output", flag, name],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def resolve_config(args: argparse.Namespace) -> tuple[str | None, str | None, str]:
    api_url = args.api_url or os.environ.get("BOOKUP_PUBLIC_API_URL")
    api_key = args.api_key or os.environ.get("BOOKUP_PUBLIC_API_KEY")
    source = "argumentos / variables de entorno"

    if not api_url or not api_key:
        print(f"Leyendo outputs de Terraform en {args.tf_dir} ...", file=sys.stderr)
        if not api_url:
            api_url = terraform_output(args.tf_dir, "public_api_url")
        if not api_key:
            raw = terraform_output(args.tf_dir, "public_api_keys", as_json=True)
            if raw:
                try:
                    api_key = json.loads(raw).get(args.consumer)
                except (ValueError, AttributeError):
                    api_key = None
        source = "terraform output"

    if api_url:
        api_url = api_url.rstrip("/")
    return api_url, api_key, source


def mask(key: str | None) -> str | None:
    if not key:
        return None
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "…"


class DemoHandler(BaseHTTPRequestHandler):
    api_url: str | None = None
    api_key: str | None = None
    consumer: str = "demo-library"
    source: str = ""

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - formato más corto
        sys.stderr.write("  %s\n" % (fmt % args))

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - nombre impuesto por http.server
        parsed = urllib.parse.urlsplit(self.path)

        if parsed.path in ("/", "/index.html", "/public-api.html"):
            body = HTML_FILE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/config":
            self.send_json(200, self.config_payload())
            return

        if parsed.path.startswith("/proxy/"):
            self.proxy(parsed.path[len("/proxy/"):], parsed.query)
            return

        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - nombre impuesto por http.server
        """Cambia la URL y la API key en caliente (el botón de configuración de la página)."""
        if urllib.parse.urlsplit(self.path).path != "/config":
            self.send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 4096:
                raise ValueError
            data = json.loads(self.rfile.read(length) or b"{}")
            api_url = str(data.get("api_url") or "").strip().rstrip("/")
            api_key = str(data.get("api_key") or "").strip()
        except (ValueError, AttributeError):
            self.send_json(400, {"error": "JSON inválido."})
            return
        if not re.match(r"^https?://[^\s/]+(/[^\s]*)?$", api_url):
            self.send_json(400, {"error": "La URL tiene que empezar con http:// o https://."})
            return
        if not api_key:
            self.send_json(400, {"error": "Falta la API key."})
            return

        cls = type(self)
        cls.api_url, cls.api_key, cls.source = api_url, api_key, "página"
        print(f"Config actualizada desde la página: {api_url} (clave {mask(api_key)})", file=sys.stderr)
        self.send_json(200, self.config_payload())

    def config_payload(self) -> dict:
        return {
            "configured": bool(self.api_url and self.api_key),
            "api_url": self.api_url,
            "consumer": self.consumer,
            "key_masked": mask(self.api_key),
            "source": self.source,
        }

    def proxy(self, path: str, query: str) -> None:
        if not (self.api_url and self.api_key):
            self.send_json(503, {"error": "La demo no tiene URL o API key configuradas."})
            return
        path = urllib.parse.unquote(path)
        if not ALLOWED_PATH.match(path):
            self.send_json(400, {"error": f"Path no expuesto por el API público: /{path}"})
            return

        target = f"{self.api_url}/{urllib.parse.quote(path)}"
        if query:
            target += f"?{query}"
        request = urllib.request.Request(
            target,
            headers={"x-api-key": self.api_key, "Accept": "application/json"},
            method="GET",
        )

        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=35) as response:
                status, headers, raw = response.status, response.headers, response.read()
        except urllib.error.HTTPError as err:
            status, headers, raw = err.code, err.headers, err.read()
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            self.send_json(
                502,
                {
                    "error": f"No se pudo llegar al API Gateway: {getattr(err, 'reason', err)}",
                    "url": target,
                },
            )
            return
        elapsed_ms = round((time.perf_counter() - started) * 1000)

        text = raw.decode("utf-8", errors="replace")
        try:
            body = json.loads(text)
        except ValueError:
            body = text

        self.send_json(
            200,
            {
                "url": target,
                "status": status,
                "elapsed_ms": elapsed_ms,
                "headers": {
                    name: headers.get(name) for name in SHOWN_HEADERS if headers.get(name)
                },
                "body": body,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", help="invoke URL del stage (output public_api_url)")
    parser.add_argument("--api-key", help="valor de la API key (header x-api-key)")
    parser.add_argument("--consumer", default="demo-library", help="consumidor de public_api_keys (default: demo-library)")
    parser.add_argument("--tf-dir", type=Path, default=DEFAULT_TF_DIR, help="directorio de Terraform con los outputs")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()

    api_url, api_key, source = resolve_config(args)
    DemoHandler.api_url, DemoHandler.api_key = api_url, api_key
    DemoHandler.consumer, DemoHandler.source = args.consumer, source

    if not (api_url and api_key):
        print(
            "\n⚠  Falta la URL o la API key: cargalas con el botón ⚙ de la página, o pasalas con\n"
            "   --api-url/--api-key o BOOKUP_PUBLIC_API_URL/BOOKUP_PUBLIC_API_KEY.\n",
            file=sys.stderr,
        )
    else:
        print(f"API Gateway: {api_url}  (consumidor {args.consumer}, clave {mask(api_key)})", file=sys.stderr)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), DemoHandler)
    print(f"Demo en http://localhost:{args.port}  (Ctrl+C para cortar)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
