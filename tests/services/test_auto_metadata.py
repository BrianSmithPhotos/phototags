from pathlib import Path

from phototags.services.auto_metadata import (
    description_with_art_filter_note,
    keywords_with_auto_tokens,
    merge_keywords,
    parse_keywords,
    sooc_token_for,
)


def test_parse_keywords_splits_on_commas_and_newlines() -> None:
    assert parse_keywords("fox, forest\nautumn, , red fox") == [
        "fox",
        "forest",
        "autumn",
        "red fox",
    ]


def test_parse_keywords_empty_text_returns_empty_list() -> None:
    assert parse_keywords("") == []


def test_merge_keywords_dedupes_case_insensitively_preserving_first_occurrence_order() -> None:
    merged = merge_keywords(["Fox", "Forest"], ["fox", "Autumn"])
    assert merged == ["Fox", "Forest", "Autumn"]


def test_sooc_token_for_jpeg_variants() -> None:
    assert sooc_token_for(Path("IMG_0001.JPG")) == "sooc"
    assert sooc_token_for(Path("IMG_0001.jpeg")) == "sooc"


def test_sooc_token_for_raw_is_empty() -> None:
    assert sooc_token_for(Path("IMG_0001.ORF")) == ""


def test_keywords_with_auto_tokens_appends_and_dedupes() -> None:
    result = keywords_with_auto_tokens(
        "fox, sooc",
        art_filter_token="Grainy Film",
        camera_token="OM-1",
        lens_token="12-40mm",
        sooc_token="sooc",
    )
    assert result == "fox, sooc, Grainy Film, OM-1, 12-40mm"


def test_keywords_with_auto_tokens_skips_blank_tokens() -> None:
    result = keywords_with_auto_tokens(
        "fox",
        art_filter_token="",
        camera_token="OM-1",
        lens_token="",
        sooc_token="",
    )
    assert result == "fox, OM-1"


def test_description_with_art_filter_note_appends_when_missing() -> None:
    result = description_with_art_filter_note("A fox in the forest.", "Grainy Film")
    assert result == "A fox in the forest. In camera effect Grainy Film."


def test_description_with_art_filter_note_skips_if_already_present() -> None:
    description = "A fox in the forest. In camera effect Grainy Film."
    assert description_with_art_filter_note(description, "Grainy Film") == description


def test_description_with_art_filter_note_no_token_is_passthrough() -> None:
    assert description_with_art_filter_note("A fox.", "") == "A fox."


def test_description_with_art_filter_note_empty_description_has_no_leading_space() -> None:
    assert description_with_art_filter_note("", "Grainy Film") == "In camera effect Grainy Film."
