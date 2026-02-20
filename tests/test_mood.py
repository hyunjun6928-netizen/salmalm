"""Tests for mood.py — Mood-Aware Response."""
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def tmp_mood(tmp_path, monkeypatch):
    monkeypatch.setattr('salmalm.mood.MOOD_DIR', tmp_path)
    monkeypatch.setattr('salmalm.mood.MOOD_CONFIG_FILE', tmp_path / 'mood.json')
    monkeypatch.setattr('salmalm.mood.MOOD_HISTORY_FILE', tmp_path / 'mood_history.json')
    return tmp_path


class TestMoodDetector:
    def test_detect_happy_korean(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('ㅋㅋㅋㅋㅋ 너무 좋아 최고야')
        assert mood == 'happy'
        assert conf > 0

    def test_detect_sad_korean(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('ㅠㅠㅠㅠ 너무 슬프다 힘들어...')
        assert mood == 'sad'

    def test_detect_angry_caps(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('THIS IS SO ANNOYING WHY DOES NOTHING WORK')
        assert mood in ('angry', 'frustrated')

    def test_detect_excited(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('대박!!! 🎉🔥 너무 신난다!!!')
        assert mood == 'excited'

    def test_detect_anxious(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('어떡하지... 걱정되고 불안해... 😰')
        assert mood == 'anxious'

    def test_detect_tired(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('피곤해 졸려 😴 지쳤어')
        assert mood == 'tired'

    def test_detect_frustrated(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('도대체 왜 안돼 답답해 모르겠다')
        assert mood == 'frustrated'

    def test_detect_neutral(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, conf = md.detect('파일을 읽어주세요')
        assert mood == 'neutral'

    def test_emoji_detection(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        mood, _ = md.detect('😭😭😭')
        assert mood == 'sad'

    def test_disabled(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        md.set_mode('off')
        mood, conf = md.detect('ㅋㅋㅋㅋ 너무 좋아')
        assert mood == 'neutral'
        assert conf == 0.0

    def test_set_mode_on(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        result = md.set_mode('on')
        assert '활성화' in result
        assert md.enabled

    def test_set_mode_sensitive(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        md.set_mode('sensitive')
        assert md.sensitivity == 'sensitive'

    def test_tone_injection(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        tone = md.get_tone_injection('angry')
        assert '차분' in tone

    def test_record_and_status(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        md.record_mood('happy', 0.8)
        status = md.get_status('ㅋㅋㅋ 좋아')
        assert '🎭' in status

    def test_generate_report_empty(self):
        from salmalm.features.mood import MoodDetector
        md = MoodDetector()
        report = md.generate_report('week')
        assert '없습니다' in report or '📊' in report
