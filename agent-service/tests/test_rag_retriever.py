from app.rag.retriever import MarkdownBusinessKnowledgeRetriever


def test_retrieves_relevant_price_and_trend_definitions() -> None:
    result = MarkdownBusinessKnowledgeRetriever().retrieve("上海月度房价趋势如何？")

    assert "monthly_trend" in result.document_ids
    assert "unit_price" in result.document_ids
    assert "listing_type = 'SALE'" in result.context
    assert result.needs_clarification is False


def test_ambiguous_value_for_money_requires_clarification() -> None:
    result = MarkdownBusinessKnowledgeRetriever().retrieve("哪个区性价比最高？")

    assert result.document_ids == ["value_for_money"]
    assert result.needs_clarification is True
    assert result.clarification_question is not None
    assert "面积/总价" in result.clarification_question
    assert "租金/面积" in result.clarification_question


def test_explicit_formula_resolves_value_for_money_ambiguity() -> None:
    result = MarkdownBusinessKnowledgeRetriever().retrieve(
        "按面积除以总价计算，哪个区性价比最高？"
    )

    assert "value_for_money" in result.document_ids
    assert result.needs_clarification is False
