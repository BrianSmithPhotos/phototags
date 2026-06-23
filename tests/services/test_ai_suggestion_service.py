from phototags.services.ai_suggestion_service import AiSuggestionResult, AiSuggestionService

# These methods are pure parsing/decision logic with no provider calls, so a
# placeholder provider (never invoked by the methods under test) is enough.
_SERVICE = AiSuggestionService(provider=object())


def test_extract_json_object_parses_plain_json() -> None:
    payload = _SERVICE._extract_json_object('{"description": "a dog", "keywords": ["dog"]}')

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_extract_json_object_strips_code_fence() -> None:
    content = '```json\n{"description": "a dog", "keywords": ["dog"]}\n```'

    payload = _SERVICE._extract_json_object(content)

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_extract_json_object_extracts_braces_from_surrounding_prose() -> None:
    content = 'Sure, here you go: {"description": "a dog", "keywords": ["dog"]} Hope that helps!'

    payload = _SERVICE._extract_json_object(content)

    assert payload == {"description": "a dog", "keywords": ["dog"]}


def test_normalize_keywords_dedupes_case_insensitively_preserving_first_casing() -> None:
    normalized = _SERVICE._normalize_keywords(["Dog", "dog", "Cat"])

    assert normalized == ["Dog", "Cat"]


def test_normalize_keywords_splits_comma_separated_string() -> None:
    normalized = _SERVICE._normalize_keywords("dog, cat,  bird ")

    assert normalized == ["dog", "cat", "bird"]


def test_normalize_keywords_returns_empty_list_for_unsupported_type() -> None:
    assert _SERVICE._normalize_keywords(None) == []
    assert _SERVICE._normalize_keywords(42) == []


def test_merge_keywords_preserves_primary_order_and_drops_secondary_duplicates() -> None:
    merged = _SERVICE._merge_keywords(["dog", "park"], ["cat", "Dog", "tree"])

    assert merged == ["dog", "park", "cat", "tree"]


def test_needs_subject_crop_refinement_true_when_keyword_subject_not_in_description() -> None:
    result = AiSuggestionResult(description="A bird perched on a branch.", keywords=["snowy egret", "branch"])

    assert _SERVICE._needs_subject_crop_refinement(result) is True


def test_needs_subject_crop_refinement_false_when_description_already_names_subject() -> None:
    result = AiSuggestionResult(description="A snowy egret perched on a branch.", keywords=["snowy egret", "branch"])

    assert _SERVICE._needs_subject_crop_refinement(result) is False


def test_needs_subject_crop_refinement_false_when_no_subject_candidates() -> None:
    result = AiSuggestionResult(description="A scenic overlook at sunset.", keywords=["sunset", "overlook"])

    assert _SERVICE._needs_subject_crop_refinement(result) is False


def test_description_mentions_subject_matches_whole_word_only() -> None:
    assert _SERVICE._description_mentions_subject("A dog runs in the park.", ["dog"]) is True
    assert _SERVICE._description_mentions_subject("A dogwood tree in bloom.", ["dog"]) is False


def test_description_mentions_subject_falls_back_to_last_token_of_multiword_candidate() -> None:
    # "egret" alone should match even though the full candidate phrase is "snowy egret".
    assert _SERVICE._description_mentions_subject("An egret stands in shallow water.", ["snowy egret"]) is True
