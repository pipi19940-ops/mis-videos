"""Crea un video con un Space gratis de Hugging Face y lo agrega a videos.json.

Se ejecuta desde el workflow "Crear video con IA". Lee la configuración de
variables de entorno: SPACE, PROMPT, IMAGEN, TITULO, ETIQUETAS, HF_TOKEN.
"""
import datetime
import json
import os
import re
import shutil
import sys

from gradio_client import Client, handle_file


def env(nombre):
    return (os.environ.get(nombre) or "").strip()


SPACE = env("SPACE")
PROMPT = env("PROMPT")
IMAGEN = env("IMAGEN")
TITULO = env("TITULO") or PROMPT[:60]
ETIQUETAS = [e.strip() for e in env("ETIQUETAS").split(",") if e.strip()]
TOKEN = env("HF_TOKEN") or None


def conectar():
    try:
        return Client(SPACE, token=TOKEN)
    except TypeError:  # versiones antiguas de gradio_client
        return Client(SPACE, hf_token=TOKEN)


def es_imagen(p):
    return (p.get("component") or "").lower() in ("image", "imageeditor")


def elegir_endpoint(api):
    endpoints = api.get("named_endpoints", {})
    candidatos = []
    for nombre, info in endpoints.items():
        nombres = [(p.get("parameter_name") or p.get("label") or "").lower() for p in info["parameters"]]
        tiene_prompt = any("prompt" in n and "neg" not in n for n in nombres)
        puntos = (3 if "video" in nombre.lower() else 0) + (2 if tiene_prompt else 0)
        if tiene_prompt:
            candidatos.append((puntos, nombre, info))
    if not candidatos:
        sys.exit(f"No encontré una función con 'prompt' en {SPACE}. Funciones: {list(endpoints)}")
    candidatos.sort(key=lambda c: -c[0])
    return candidatos[0][1], candidatos[0][2]


def armar_argumentos(info):
    args = {}
    for p in info["parameters"]:
        nombre = p.get("parameter_name")
        n = (nombre or "").lower()
        if "prompt" in n and "neg" not in n:
            args[nombre] = PROMPT
        elif es_imagen(p):
            if IMAGEN:
                args[nombre] = handle_file(IMAGEN)
            elif not p.get("parameter_has_default"):
                sys.exit(
                    f"El Space {SPACE} necesita una imagen. Llena el campo 'imagen' "
                    "o usa un Space de texto a video."
                )
        elif not p.get("parameter_has_default"):
            sys.exit(f"El Space {SPACE} pide el dato '{nombre}' y no sé qué poner. Mándale el error a Claude.")
    return args


def buscar_video(resultado):
    """Busca la ruta de un archivo de video dentro de la respuesta del Space."""
    if isinstance(resultado, str) and re.search(r"\.(mp4|webm|mov)$", resultado, re.I) and os.path.exists(resultado):
        return resultado
    if isinstance(resultado, dict):
        resultado = list(resultado.values())
    if isinstance(resultado, (list, tuple)):
        for r in resultado:
            encontrado = buscar_video(r)
            if encontrado:
                return encontrado
    return None


def main():
    if not PROMPT:
        sys.exit("Falta el prompt.")
    print(f"Conectando a {SPACE}…")
    cliente = conectar()
    nombre, info = elegir_endpoint(cliente.view_api(print_info=False, return_format="dict"))
    args = armar_argumentos(info)
    print(f"Usando {nombre} con {list(args)}")
    resultado = cliente.predict(api_name=nombre, **args)
    origen = buscar_video(resultado)
    if not origen:
        sys.exit(f"El Space no devolvió un video. Respuesta: {resultado}")

    os.makedirs("videos", exist_ok=True)
    marca = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = f"videos/ia-{marca}{os.path.splitext(origen)[1].lower()}"
    shutil.copy(origen, destino)
    if os.path.getsize(destino) > 95 * 1024 * 1024:
        sys.exit("El video pesa más de 95 MB y GitHub no lo acepta.")

    with open("videos.json", encoding="utf-8") as f:
        videos = json.load(f)
    videos.append({
        "titulo": TITULO,
        "url": destino,
        "descripcion": f"Creado con IA ({SPACE}). Prompt: {PROMPT}",
        "etiquetas": ETIQUETAS or ["ia"],
        "fecha": datetime.date.today().isoformat(),
    })
    with open("videos.json", "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Listo: {destino}")


if __name__ == "__main__":
    main()
