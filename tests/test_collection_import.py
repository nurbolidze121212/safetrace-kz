import pytest

from scripts.import_collection import batches, srt, telegram


def test_telegram_preserves_rich_link_timestamp_and_source_id():
    rows, notes = telegram({"id": 123, "name": "Test", "messages": [
        {"id": 4, "type": "message", "date_unixtime": "0", "text": ["Look ",
            {"type": "text_link", "text": "here", "href": "https://example.test/"}]},
        {"id": 5, "type": "service"}, {"id": 6, "type": "message", "text": ""},
    ]})
    assert rows[0]["text"] == "Look here (https://example.test/)"
    assert rows[0]["published_at"] == "1970-01-01T00:00:00+00:00"
    assert "message:4" in rows[0]["source"] and notes["skipped_service_or_empty"] == 2


def test_timecoded_transcript_preserves_interval_and_rejects_reversed_time():
    rows, _ = srt("1\n00:01:03,100 --> 00:01:05,900\nТіркел, бонус ал!\n")
    assert "00:01:03,100" in rows[0]["source"] and "Тіркел" in rows[0]["text"]
    with pytest.raises(ValueError, match="end after"):
        srt("1\n00:01:05,000 --> 00:01:03,000\ntext")


def test_collection_batches_without_losing_last_item():
    messages = [{"text": str(i), "source": "test"} for i in range(43)]
    result = batches(messages, "Import")
    assert [len(p["materials"]) for p in result] == [20, 20, 3]
    assert [m for p in result for m in p["materials"]] == messages
    with pytest.raises(ValueError):
        batches(messages * 24, "oversized")
