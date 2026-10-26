from backend.app.translate.parser import parse_translations, strip_think


def test_strip_think_closed_and_unclosed():
    assert strip_think("<think>hidden</think>hello").strip() == "hello"
    assert strip_think("prefix<think>hidden").strip() == "prefix"
    assert strip_think("normal text") == "normal text"


def test_parse_with_fence_and_think():
    raw = "\x60\x60\x60json\n<think>plan</think>\n{\"translations\":[{\"id\":\"a\",\"text\":\"A\"}]}\n\x60\x60\x60"
    result, issues = parse_translations(raw, ["a"])
    assert result == {"a": "A"}
    assert issues["missing"] == []


def test_parse_reports_missing_and_unknown():
    raw = '{"translations":[{"id":"a","text":"A"},{"id":"zzz","text":"X"}]}'
    result, issues = parse_translations(raw, ["a", "b"])
    assert result == {"a": "A"}
    assert issues["missing"] == ["b"]
    assert "zzz" in issues["unknown"]


def test_parse_truncated_json():
    raw = '{"translations":[{"id":"a","text":"A"'
    result, issues = parse_translations(raw, ["a"])
    assert result == {}
    assert issues["truncated"] is True
    assert issues["missing"] == ["a"]


def test_parse_duplicate_and_empty():
    raw = '{"translations":[{"id":"a","text":"A"},{"id":"a","text":"B"},{"id":"b","text":"  "}]}'
    result, issues = parse_translations(raw, ["a", "b"])
    assert result == {"a": "A"}
    assert "a" in issues["duplicated"]
    assert "b" in issues["empty"]
