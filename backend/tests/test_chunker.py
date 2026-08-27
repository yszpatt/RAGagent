from app.ingestion.chunkers.recursive import recursive_chunk


def test_chunk_splits_long_text():
    text = "句子。" * 2000  # 超长文本
    chunks = recursive_chunk(text, chunk_size=200, overlap=40)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)


def test_chunk_short_text_single():
    chunks = recursive_chunk("短文本", chunk_size=200, overlap=40)
    assert len(chunks) == 1
    assert chunks[0] == "短文本"


def test_chunk_preserves_content():
    text = "A" * 100 + "SEP" + "B" * 100
    chunks = recursive_chunk(text, chunk_size=100, overlap=20)
    assert "SEP" in "".join(chunks)


def test_chunk_empty_text():
    assert recursive_chunk("") == []
    assert recursive_chunk("   ") == []
