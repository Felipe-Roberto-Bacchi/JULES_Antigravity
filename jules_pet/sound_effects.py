"""Procedural 8-bit chiptune sound effect synthesizer and playback engine."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
import io
import math
import os
import random
import struct
import wave

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows platforms
    winsound = None  # type: ignore[assignment]

SAMPLE_RATE = 22050
_MAX_AMPLITUDE = int(32767 * 0.35)


class SoundEffect(Enum):
    """Supported 8-bit procedural sound effects."""

    BLIP = "blip"
    POWER_UP = "power_up"
    SQUIRT = "squirt"
    LEVEL_UP = "level_up"


def _clamp_sample(value: float) -> int:
    """Convert a normalized [-1.0, 1.0] float sample to signed 16-bit PCM."""
    scaled = int(max(-1.0, min(1.0, value)) * _MAX_AMPLITUDE)
    return max(-32768, min(32767, scaled))


def _square_wave(phase: float, duty: float = 0.5) -> float:
    return 1.0 if (phase % 1.0) < duty else -1.0


def _triangle_wave(phase: float) -> float:
    frac = phase % 1.0
    return 4.0 * frac - 1.0 if frac < 0.5 else 3.0 - 4.0 * frac


def _render_tone_sequence(
    notes: list[tuple[float, float]],
    *,
    duty: float = 0.5,
    decay: float = 4.0,
) -> list[int]:
    """Render a sequence of (frequency_hz, duration_seconds) square-wave notes."""
    samples: list[int] = []
    phase = 0.0
    for freq, duration in notes:
        total_frames = max(1, int(SAMPLE_RATE * duration))
        for idx in range(total_frames):
            t = idx / total_frames
            # Crisp attack, exponential chiptune decay
            attack = min(1.0, idx / max(1, int(SAMPLE_RATE * 0.004)))
            envelope = attack * math.exp(-decay * t)
            samples.append(_clamp_sample(_square_wave(phase, duty) * envelope))
            phase += freq / SAMPLE_RATE
    return samples


def _synth_blip() -> list[int]:
    return _render_tone_sequence([(660.0, 0.035), (880.0, 0.045)], duty=0.5, decay=5.0)


def _synth_power_up() -> list[int]:
    return _render_tone_sequence(
        [(523.25, 0.06), (659.25, 0.06), (783.99, 0.06), (1046.50, 0.10)],
        duty=0.25,
        decay=3.0,
    )


def _synth_squirt() -> list[int]:
    duration = 0.16
    total_frames = int(SAMPLE_RATE * duration)
    rng = random.Random(1337)
    samples: list[int] = []
    phase = 0.0
    for idx in range(total_frames):
        t = idx / total_frames
        freq = 920.0 - 680.0 * t
        envelope = math.exp(-4.5 * t)
        tone = _triangle_wave(phase)
        noise = rng.uniform(-1.0, 1.0)
        mixed = (0.65 * tone + 0.35 * noise) * envelope
        samples.append(_clamp_sample(mixed))
        phase += freq / SAMPLE_RATE
    return samples


def _synth_level_up() -> list[int]:
    return _render_tone_sequence(
        [
            (523.25, 0.08),
            (659.25, 0.08),
            (783.99, 0.08),
            (1046.50, 0.20),
        ],
        duty=0.5,
        decay=2.2,
    )


_GENERATORS: dict[SoundEffect, Callable[[], list[int]]] = {
    SoundEffect.BLIP: _synth_blip,
    SoundEffect.POWER_UP: _synth_power_up,
    SoundEffect.SQUIRT: _synth_squirt,
    SoundEffect.LEVEL_UP: _synth_level_up,
}

_WAV_CACHE: dict[SoundEffect, bytes] = {}


def _pack_wav(samples: list[int]) -> bytes:
    """Encode 16-bit mono PCM samples at 22050 Hz into an in-memory WAV buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


def synthesize_wav_bytes(effect: SoundEffect) -> bytes:
    """Return cached 16-bit mono 22050 Hz WAV bytes for the given SoundEffect."""
    cached = _WAV_CACHE.get(effect)
    if cached is not None:
        return cached

    generator = _GENERATORS.get(effect)
    if generator is None:
        raise ValueError(f"Unsupported SoundEffect: {effect!r}")

    wav_bytes = _pack_wav(generator())
    _WAV_CACHE[effect] = wav_bytes
    return wav_bytes


def _default_play_wav(wav_bytes: bytes) -> None:
    """Play WAV bytes asynchronously via winsound when running with a live desktop."""
    if os.environ.get("QT_QPA_PLATFORM", "").lower() in {"offscreen", "minimal"}:
        return
    if winsound is None:
        return
    winsound.PlaySound(
        wav_bytes,
        winsound.SND_MEMORY | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
    )


class RetroSoundEngine:
    """Opt-in procedural 8-bit sound player with injectable backend."""

    def __init__(
        self,
        enabled: bool = False,
        player: Callable[[bytes], None] | None = None,
    ) -> None:
        self._enabled = bool(enabled)
        self._player = player if player is not None else _default_play_wav

    @property
    def enabled(self) -> bool:
        """Whether sound playback is currently enabled."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable sound playback."""
        self._enabled = bool(enabled)

    def play(self, effect: SoundEffect) -> None:
        """Synthesize and play `effect` if enabled, swallowing backend errors."""
        if not self._enabled:
            return
        wav_bytes = synthesize_wav_bytes(effect)
        try:
            self._player(wav_bytes)
        except Exception:
            pass
