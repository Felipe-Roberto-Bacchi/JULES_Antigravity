"""Tests for 8-bit procedural sound synthesizer and RetroSoundEngine."""

from __future__ import annotations

import io
import struct
import wave

import pytest

from jules_pet.sound_effects import RetroSoundEngine, SoundEffect, synthesize_wav_bytes


def test_sound_effect_enum_members() -> None:
    assert SoundEffect.BLIP.name == "BLIP"
    assert SoundEffect.POWER_UP.name == "POWER_UP"
    assert SoundEffect.SQUIRT.name == "SQUIRT"
    assert SoundEffect.LEVEL_UP.name == "LEVEL_UP"
    assert len(SoundEffect) == 4


@pytest.mark.parametrize("effect", list(SoundEffect))
def test_synthesize_wav_bytes_produces_valid_16bit_mono_22050hz_wav(
    effect: SoundEffect,
) -> None:
    wav_bytes = synthesize_wav_bytes(effect)

    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44
    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes[:16]

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 22050
        assert wf.getcomptype() == "NONE"
        nframes = wf.getnframes()
        assert nframes > 0
        raw_frames = wf.readframes(nframes)

    samples = struct.unpack(f"<{nframes}h", raw_frames)
    assert max(abs(sample) for sample in samples) > 0


def test_all_sound_effects_have_distinct_waveforms_and_are_cached() -> None:
    buffers = {effect: synthesize_wav_bytes(effect) for effect in SoundEffect}
    assert len(set(buffers.values())) == 4

    frame_counts = {}
    for effect, buf in buffers.items():
        with wave.open(io.BytesIO(buf), "rb") as wf:
            frame_counts[effect] = wf.getnframes()
        # Deterministic and cached
        assert synthesize_wav_bytes(effect) is buf

    # Not all effects have the exact same duration
    assert len(set(frame_counts.values())) >= 3


def test_retro_sound_engine_defaults_disabled_and_skips_playback() -> None:
    played: list[bytes] = []
    default_engine = RetroSoundEngine()
    assert default_engine.enabled is False

    engine = RetroSoundEngine(player=played.append)
    assert engine.enabled is False

    engine.play(SoundEffect.BLIP)
    engine.play(SoundEffect.LEVEL_UP)
    assert played == []


def test_retro_sound_engine_plays_when_enabled_and_respects_toggle() -> None:
    played: list[bytes] = []
    engine = RetroSoundEngine(player=played.append)

    engine.set_enabled(True)
    assert engine.enabled is True

    engine.play(SoundEffect.POWER_UP)
    engine.play(SoundEffect.SQUIRT)

    assert played == [
        synthesize_wav_bytes(SoundEffect.POWER_UP),
        synthesize_wav_bytes(SoundEffect.SQUIRT),
    ]

    engine.set_enabled(False)
    assert engine.enabled is False
    engine.play(SoundEffect.BLIP)
    assert len(played) == 2


def test_retro_sound_engine_catches_player_exceptions_safely() -> None:
    def failing_player(_wav_bytes: bytes) -> None:
        raise RuntimeError("audio backend failure")

    engine = RetroSoundEngine(player=failing_player)
    engine.set_enabled(True)

    # Should not raise
    engine.play(SoundEffect.LEVEL_UP)


def test_retro_sound_engine_default_backend_safe_in_offscreen_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    engine = RetroSoundEngine()
    engine.set_enabled(True)

    # Should be a safe no-op in offscreen/headless mode
    engine.play(SoundEffect.BLIP)
