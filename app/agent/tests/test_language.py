import pytest

from app.agent.language import detect_language, is_foreign_paragraph


@pytest.mark.parametrize(
    "text,code",
    [
        ("Tổng quan các nghiên cứu về mô hình ngôn ngữ lớn trong đánh giá tự động", "vi"),
        ("A comprehensive survey of retrieval-augmented generation for the evaluation of language models", "en"),
        ("Une étude de la génération augmentée par la recherche pour les modèles de langage dans le domaine", "fr"),
        ("Un estudio de la generación aumentada por recuperación para los modelos de lenguaje en el campo", "es"),
        ("Eine Untersuchung der abrufgestützten Generierung für die Bewertung von Sprachmodellen und die", "de"),
        ("大规模语言模型在自动评估中的应用综述", "zh"),
        ("大規模言語モデルの自動評価に関するサーベイ", "ja"),
        ("대규모 언어 모델의 자동 평가에 관한 연구", "ko"),
        ("Обзор методов генерации с дополнением поиском для оценки языковых моделей", "ru"),
        ("", "en"),
    ],
)
def test_detect_language(text, code):
    assert detect_language(text) == code


def test_is_foreign_paragraph():
    en = "This paragraph is written in English and has enough words to be classified reliably by the detector."
    assert is_foreign_paragraph(en, "vi")
    assert not is_foreign_paragraph(en, "en")
    assert not is_foreign_paragraph("Short text.", "vi")


def test_english_only_rule_is_in_chat_and_clarify_prompts():
    from app.agent.clarify import _SYSTEM_PROMPT as clarify_prompt
    from app.agent.language import ENGLISH_ONLY_RULE, STANDARD_LANGUAGE
    from app.api.routes.chat import _SYSTEM_PROMPT as chat_prompt

    assert STANDARD_LANGUAGE == "en"
    assert ENGLISH_ONLY_RULE in chat_prompt
    assert ENGLISH_ONLY_RULE in clarify_prompt
