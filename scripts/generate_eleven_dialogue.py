#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = "https://api.elevenlabs.io"
API_KEY = os.environ.get("ELEVENLABS_API_KEY")
SOFIA_NAME = os.environ.get("SOFIA_VOICE_NAME", "Sofia - Natural Conversations")
TONY_NAME = os.environ.get("TONY_VOICE_NAME", "Tony - Expressive, Fast and Spontaneous")
MODEL_ID = "eleven_v3"
OUTPUT_FORMAT = "mp3_44100_128"
MAX_CHARS = 1900

if not API_KEY:
    raise SystemExit("Falta ELEVENLABS_API_KEY en el entorno.")


def api_get(path, params=None):
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"xi-api-key": API_KEY})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def api_post(path, payload, params=None):
    url = API_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"xi-api-key": API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def find_voice(name):
    data = api_get("/v2/voices", {"search": name, "page_size": 100})
    voices = data.get("voices", [])
    exact = [v for v in voices if v.get("name") == name]
    if len(exact) == 1:
        return exact[0]["voice_id"]
    if len(exact) > 1:
        raise SystemExit(f"Hay varias voces con el nombre exacto: {name}")
    raise SystemExit(
        f"No encuentro la voz exacta '{name}'. Voces devueltas: "
        + ", ".join(v.get("name", "") for v in voices[:20])
    )


def read_dialogue(path):
    turns = []
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            speaker, text = line.split("|", 1)
        except ValueError:
            raise SystemExit(f"Línea {n}: usa FORMATO SPEAKER|texto")
        speaker = speaker.strip().upper()
        text = text.strip()
        if speaker not in {"SOFIA", "TONY"}:
            raise SystemExit(f"Línea {n}: hablante desconocido '{speaker}'")
        if not text:
            raise SystemExit(f"Línea {n}: texto vacío")
        turns.append((speaker, text))
    if not turns:
        raise SystemExit("dialogue.txt está vacío")
    return turns


def chunk_turns(turns):
    chunks, current = [], []
    chars = 0
    for turn in turns:
        n = len(turn[1])
        if current and chars + n > MAX_CHARS:
            chunks.append(current)
            current, chars = [], 0
        if n > MAX_CHARS:
            raise SystemExit("Una intervención individual supera 1900 caracteres; divídela.")
        current.append(turn)
        chars += n
    if current:
        chunks.append(current)
    return chunks


def main():
    input_path = sys.argv[1] if len(sys.argv) > 1 else "dialogue.txt"
    output = Path(sys.argv[2] if len(sys.argv) > 2 else "sofia-tony.mp3")
    turns = read_dialogue(input_path)
    voice_ids = {
        "SOFIA": find_voice(SOFIA_NAME),
        "TONY": find_voice(TONY_NAME),
    }
    chunks = chunk_turns(turns)
    temp_dir = Path(".dialogue_parts")
    temp_dir.mkdir(exist_ok=True)
    parts = []

    for i, chunk in enumerate(chunks, 1):
        payload = {
            "inputs": [
                {"text": text, "voice_id": voice_ids[speaker]}
                for speaker, text in chunk
            ],
            "model_id": MODEL_ID,
            "language_code": "es",
        }
        print(f"Generando bloque {i}/{len(chunks)} ({sum(len(t) for _, t in chunk)} caracteres)...")
        audio = api_post(
            "/v1/text-to-dialogue",
            payload,
            {"output_format": OUTPUT_FORMAT},
        )
        part = temp_dir / f"part-{i:03d}.mp3"
        part.write_bytes(audio)
        parts.append(part)

    if len(parts) == 1:
        output.write_bytes(parts[0].read_bytes())
    else:
        concat = temp_dir / "concat.txt"
        concat.write_text("\n".join(f"file '{p.resolve()}'" for p in parts) + "\n", encoding="utf-8")
        import subprocess
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(output)],
            check=True,
        )
    print(f"OK: {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
