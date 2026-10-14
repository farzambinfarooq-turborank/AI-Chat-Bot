import os
import io
import wave
import logging
import subprocess
from typing import Optional

from google import genai
from google.genai import types


# ==========================================================
# ENVIRONMENT
# ==========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing from .env")


# ==========================================================
# MODEL CONFIGURATION
#
# STT_MODEL  -> any current Gemini model that accepts audio
#               input (same family used for text replies works
#               fine for transcription too).
# TTS_MODEL  -> a Gemini TTS model (audio-only output).
# VOICE_NAME -> a prebuilt Gemini voice. "Kore" reads calm and
#               professional. Preview others in Google AI
#               Studio's Voice Library before changing this.
# ==========================================================

STT_MODEL = os.getenv("GEMINI_STT_MODEL", "gemini-3.6-flash")
STT_FALLBACK_MODEL = os.getenv("GEMINI_STT_FALLBACK_MODEL", "gemini-3.8-flash")
TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
VOICE_NAME = os.getenv("GEMINI_TTS_VOICE", "Kore")

TTS_SAMPLE_RATE = 24000
TTS_SAMPLE_WIDTH = 2  # 16-bit PCM
TTS_CHANNELS = 1


# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("voice_agent")


# ==========================================================
# GEMINI CLIENT
# ==========================================================

client = genai.Client(api_key=GEMINI_API_KEY)


# ==========================================================
# TRANSCRIPTION PROMPT
#
# IMPORTANT: we ask Gemini to transcribe only — not translate,
# not clean up, not answer. The raw transcript then flows
# through the EXACT SAME text pipeline (ai_agent.py) that
# already handles Roman Urdu / Urdu / English mixed input.
# ==========================================================

TRANSCRIPTION_INSTRUCTION = (
    "Transcribe exactly what is spoken in this audio. "
    "Keep the original language and script as spoken "
    "(Roman Urdu, Urdu script, or English — whichever was "
    "used). Do not translate. Do not paraphrase. Do not add "
    "punctuation commentary or explanations. Output ONLY the "
    "transcription text, nothing else. If the audio is "
    "silent or unintelligible, output nothing."
)


# ==========================================================
# SPEECH-TO-TEXT
# ==========================================================

def transcribe_audio_bytes(
    audio_bytes: bytes,
    mime_type: str,
) -> Optional[str]:

    if not audio_bytes:
        return None

    # Primary model 503/404 de to fallback model par try karte hain,
    # taake voice notes bhi text messages ki tarah fail na hon.
    models_to_try = [STT_MODEL]

    if STT_FALLBACK_MODEL and STT_FALLBACK_MODEL != STT_MODEL:
        models_to_try.append(STT_FALLBACK_MODEL)

    for model_name in models_to_try:

        try:

            response = client.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type=mime_type,
                    ),
                    TRANSCRIPTION_INSTRUCTION,
                ],
            )

            text = (response.text or "").strip()

            if not text:
                logger.warning(
                    "Transcription returned empty text (model=%s).",
                    model_name,
                )
                continue

            logger.info(
                "Transcribed voice note (%d chars, model=%s).",
                len(text),
                model_name,
            )

            return text

        except Exception as e:

            logger.warning(
                "Transcription failed (model=%s): %s",
                model_name,
                e,
            )

    return None


# ==========================================================
# PCM -> OGG/OPUS
#
# WhatsApp only renders an incoming audio message as a proper
# "voice note" bubble (mic icon + waveform) when the file is
# audio/ogg with the Opus codec, mono. Gemini TTS returns raw
# 24kHz/16-bit PCM, so we wrap it as WAV first, then transcode
# to OGG/Opus by calling the `ffmpeg` binary directly.
#
# NOTE: we intentionally avoid the `pydub` package here — it
# imports the stdlib `audioop` module, which was REMOVED from
# Python 3.13 (PEP 594), so `import pydub` crashes on 3.13
# with "ModuleNotFoundError: No module named 'pyaudioop'".
# Calling ffmpeg directly via subprocess sidesteps that
# entirely and has one less dependency.
#
# REQUIRES: the `ffmpeg` binary to be installed on the server.
# On Railway, add a nixpacks.toml with:
#
#   [phases.setup]
#   aptPkgs = ["ffmpeg"]
#
# ==========================================================

def _pcm_to_ogg_opus(pcm_bytes: bytes) -> bytes:

    wav_buffer = io.BytesIO()

    with wave.open(wav_buffer, "wb") as wf:

        wf.setnchannels(TTS_CHANNELS)
        wf.setsampwidth(TTS_SAMPLE_WIDTH)
        wf.setframerate(TTS_SAMPLE_RATE)
        wf.writeframes(pcm_bytes)

    wav_bytes = wav_buffer.getvalue()

    process = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-y",
            "-f", "wav",
            "-i", "pipe:0",
            "-c:a", "libopus",
            "-ar", "48000",
            "-ac", "1",
            "-f", "ogg",
            "pipe:1",
        ],
        input=wav_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if process.returncode != 0:

        logger.error(
            "ffmpeg PCM->OGG conversion failed: %s",
            process.stderr.decode(errors="replace"),
        )

        raise RuntimeError("ffmpeg conversion failed")

    return process.stdout


# ==========================================================
# TEXT-TO-SPEECH
# ==========================================================

def synthesize_speech_ogg(
    text: str,
    voice_name: str = VOICE_NAME,
) -> Optional[bytes]:

    if not text or not text.strip():
        return None

    try:

        response = client.models.generate_content(
            model=TTS_MODEL,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        )
                    )
                ),
            ),
        )

        candidates = response.candidates

        if not candidates:
            logger.warning("TTS returned no candidates.")
            return None

        parts = candidates[0].content.parts

        if not parts:
            logger.warning("TTS returned no audio parts.")
            return None

        pcm_bytes = parts[0].inline_data.data

        if not pcm_bytes:
            logger.warning("TTS returned empty audio data.")
            return None

        ogg_bytes = _pcm_to_ogg_opus(pcm_bytes)

        logger.info(
            "Synthesized voice reply (%d bytes ogg).",
            len(ogg_bytes),
        )

        return ogg_bytes

    except Exception as e:

        logger.exception("Speech synthesis failed: %s", e)

        return None