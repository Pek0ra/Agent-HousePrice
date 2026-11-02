import json
import shutil
from pathlib import Path

from app.agents.routing_policy import decide_route
from app.rag.policy_index import CORPUS, chunks, load_corpus
from app.rag.policy_store import PolicyStore
from app.tools.registry import build_tool_registry
from app.config import Settings
from app.agents.mysql_agent import MysqlNaturalLanguageAgent
from tests.test_function_calling import Audit, StaticJev


class TinyEmbedding:
    def embed(self, texts):
        import numpy as np
        for text in texts:
            yield np.array([len(text) % 17 + 1, text.count("公积金") + 1, text.count("契税") + 1], dtype=float)


def test_corpus_review_dates_and_provenance():
    files, report = load_corpus()
    assert len(files) == len(report) == 8
    assert sum(f.status == "needs_manual_review" for f in files) == 0
    assert all(f.status == "machine_checked" for f in files)
    derived = next(f for f in files if f.metadata["version_id"] == "bj-housing-2026-400")
    assert derived.effective_from == "2026-08-08" and derived.effective_check == "derived_unverified"
    unknown = next(f for f in files if f.metadata["version_id"] == "bj-gjj-rate-2025-05-08")
    assert unknown.effective_from is None and unknown.effective_check == "unknown"
    assert all(c["content"] and c["source_url"].startswith("https://") for f in files for c in chunks(f))


def test_qdrant_idempotence_and_review_filter(tmp_path):
    corpus = tmp_path / "corpus"
    shutil.copytree(CORPUS, corpus)
    store = PolicyStore(str(tmp_path / "qdrant"), model=TinyEmbedding())
    first = store.build(corpus)
    assert sum(row["updated_chunks"] for row in first) > 0
    second = store.build(corpus)
    assert sum(row["updated_chunks"] for row in second) == 0
    assert store.inspect()["points"] == sum(row["chunks"] for row in first)
    changed_file = corpus / "tax-2024-16.md"
    changed_file.write_text(changed_file.read_text(encoding="utf-8").replace("140平方米", "141平方米", 1), encoding="utf-8")
    changed = store.build(corpus)
    assert sum(row["updated_chunks"] for row in changed) == 1
    assert store.inspect()["points"] == sum(row["chunks"] for row in first)
    found = store.search("京建发〔2025〕565号公积金二套首付")
    assert any(p["version_id"] == "bj-housing-2025-565-bulletin" and "25%" in p["content"]
               for p in found["evidence"])
    assert all(p["review_status"] == "machine_checked" for p in store.search("公积金贷款")["evidence"])
    historic = store.search("2024年非京籍五环内社保年限", as_of="2024-10-01")
    assert all(p["publication_date"] <= "2024-10-01" for p in historic["evidence"])
    assert not any(p["version_id"] == "bj-housing-2026-400" for p in historic["evidence"])
    conflict = store.search("非京籍家庭在五环内买房需要连续缴纳几年社保")
    assert conflict["evidence"]
    assert all(p["source_url"] and p["document_number"] for p in conflict["evidence"])
    retroactive = store.search("2026年1月1日换购住房个税退税需在旧房出售后多久买新房",
        as_of="2026-01-01")
    assert any(item["version_id"] == "tax-2026-3" for item in retroactive["evidence"])
    assert any("之后才发布" in note for note in retroactive["limitations"])
    assert not any("旧条款" in note for note in retroactive["limitations"])
    known_then = store.search("2026年1月1日当时已发布的换购住房退税政策",
        as_of="2026-01-01", published_by_date=True)
    assert not known_then["evidence"]
    expired = store.search("2028年换房还一定能享受2026年第3号公告退税吗", as_of="2028-01-01")
    assert not expired["evidence"] and any("2027-12-31" in note for note in expired["limitations"])
    assert not store.search("天津市今年购房限购年限是多少", city="天津市")["evidence"]
    store.client.close()


def test_provident_rate_question_stays_on_rate_notice(tmp_path):
    store = PolicyStore(str(tmp_path / "qdrant"), model=TinyEmbedding())
    store.build()
    for question in (
        "公积金利率文件的生效日能从已有字段直接确认吗？",
        "2025年5月8日公积金贷款利率公告何时执行？",
    ):
        result = store.search(question, limit=10)
        evidence = result["evidence"]
        assert evidence
        assert all(item["version_id"] == "bj-gjj-rate-2025-05-08" for item in evidence)
        assert all(item["policy_subject"] == "provident_loan_interest_rate" for item in evidence)
        assert all("2025年5月8日" in item["content"] for item in evidence[:2])
        assert any("2025年5月8日（含）之后新发放" in item["content"] for item in evidence)
        assert any("2026年1月1日（含）开始" in item["content"] for item in evidence)
        assert any("生效日期未知" in note for note in result["limitations"])
    unrelated = store.search("公积金二套住房最低首付款比例", limit=10)
    assert unrelated["evidence"]
    assert all(item["policy_subject"] == "provident_second_down_payment"
               for item in unrelated["evidence"])
    store.client.close()


def test_direct_policy_conclusions_require_retrieved_facts(tmp_path):
    from app.rag.policy_conclusions import direct_policy_conclusion
    from app.rag.policy_scope import policy_query_date
    store = PolicyStore(str(tmp_path / "qdrant"), model=TinyEmbedding())
    store.build()
    rate_question = "公积金利率文件的生效日能从已有字段直接确认吗？"
    rate = store.search(rate_question)["evidence"]
    answer = direct_policy_conclusion(rate_question, rate)
    assert "effective_date为unknown" in answer
    assert "新发放与存量贷款" in answer and "2026年1月1日" in answer
    assert direct_policy_conclusion(rate_question, rate[:1]) is None
    retro_question = "按后来发布但追溯适用的文件，2026 年 1 月 5 日换购住房是否落在其适用期间？"
    as_of, published = policy_query_date(retro_question)
    retro = store.search(retro_question, as_of=as_of, published_by_date=published)["evidence"]
    answer = direct_policy_conclusion(retro_question, retro)
    assert "是，2026年1月5日落在" in answer
    assert "1月12日才公布" in answer
    assert direct_policy_conclusion(retro_question, []) is None
    change_question = "2026 年 8 月前后五环内非京籍家庭购房条件是否有变化？"
    change = store.search(change_question)["evidence"]
    answer = direct_policy_conclusion(change_question, change)
    assert "满3年" in answer and "满2年" in answer and "满1年" in answer
    assert "2026年8月8日" in answer and "推算" in answer
    assert direct_policy_conclusion(change_question, change[:1]) is None
    store.client.close()


def test_policy_route_and_mcp_permissions():
    assert decide_route("policy", "policy", hive_available=False, multiple_tasks=False,
        has_history=False, depends_on_previous=False).source == "policy"
    assert decide_route("policy_listing", "current_listing", hive_available=False, multiple_tasks=True,
        has_history=False, depends_on_previous=False).tables == ("v_agent_house_listing",)
    class StubStore:
        def search(self, *args, **kwargs):
            return {"retrieved_at": "2026-10-22T00:00:00Z", "evidence": [], "limitations": []}
    registry = build_tool_registry(settings=Settings(), source="policy", selected_tables=set(),
        mysql_database=None, policy_store=StubStore())
    assert registry.names == ("search_policy", "read_policy_clause")
    assert registry.invoke("query_mysql_readonly", {"sql": "SELECT 1"}).error.code == "unavailable"


def test_policy_mcp_outage_does_not_fabricate_answer(tmp_path):
    class MissingMcp:
        names = ("search_policy", "read_policy_clause")
        def invoke(self, *_args, **_kwargs):
            raise RuntimeError("connection lost")
    agent = MysqlNaturalLanguageAgent(Settings(checkpoint_db_path=str(tmp_path / "agent.sqlite")),
        audit_repository=Audit(), jev_client=StaticJev("policy", "policy"),
        mcp_client_factory=lambda source, tables: MissingMcp())
    answer = agent.ask("首套住房契税是多少？")
    assert answer.details.data_source == "policy"
    assert "无法核对政策结论" in answer.answer
    assert "优惠金额" in answer.answer


def test_final_policy_answer_rejects_other_city_and_expired_clause(tmp_path):
    from tests.test_function_calling import Audit, StaticJev
    store = PolicyStore(str(tmp_path / "qdrant"), model=TinyEmbedding())
    store.build()
    settings = Settings(checkpoint_db_path=str(tmp_path / "agent.sqlite"))
    agent = MysqlNaturalLanguageAgent(settings, audit_repository=Audit(),
        jev_client=StaticJev("policy", "policy"),
        mcp_client_factory=lambda source, tables: build_tool_registry(
            settings=settings, source=source, selected_tables=tables,
            mysql_database=None, policy_store=store))
    other = agent.ask("天津市今年购房限购年限是多少？")
    assert "仅覆盖北京市" in other.answer and "天津" in other.answer
    assert not other.details.policy_evidence
    assert other.details.policy_tool_calls[0]["status"] == "scope_rejected"
    expired = agent.ask("2028年换房还一定能享受2026年第3号公告退税吗？")
    assert "2027-12-31" in expired.answer and "不能证明" in expired.answer
    assert not expired.details.policy_evidence
    assert expired.details.policy_tool_call_count == 1
    assert expired.details.policy_tool_calls[0]["trace_id"] == expired.trace_id
    langfang = agent.ask("河北廊坊购房社保年限可以按北京五环外政策计算吗？")
    assert "仅覆盖北京市" in langfang.answer and "廊坊" in langfang.answer
    assert not langfang.details.policy_evidence
    spaced_expiry = agent.ask("2028 年 1 月 2 日出售旧房，已有资料足以确认可退个税吗？")
    assert "2027-12-31" in spaced_expiry.answer and "不能证明" in spaced_expiry.answer
    assert not spaced_expiry.details.policy_evidence
    announced_later = agent.ask("站在 2026 年 1 月 5 日，当时已经公布的换购退税公告有哪些？")
    assert not announced_later.details.policy_evidence
    assert "未找到足够依据" in announced_later.answer
    for question in ("京建发〔2025〕360 号能否作为正式限购结论依据？",
                     "2025 年第 565 号公报的公积金条款现在能直接引用吗？"):
        reviewed = agent.ask(question)
        assert reviewed.details.policy_evidence
        assert "仍需人工核对" not in reviewed.answer
        assert reviewed.answer.startswith("可以引用")
    store.client.close()


def test_structured_clause_context_and_file_notices():
    from app.rag.policy_index import chunks, load_corpus, relate_versions
    files, _ = load_corpus()
    by_version = {item.metadata["version_id"]: item for item in files}
    notice = by_version["bj-housing-2025-565-bulletin"]
    assert "2025年12月24日起施行" in notice.enactment_text
    assert "原有政策与本通知不一致" in notice.precedence_text
    tax_notice = by_version["tax-2024-16"]
    assert "2024年12月1日起执行" in tax_notice.enactment_text
    cap = chunks(by_version["bj-housing-2026-400"])
    green = next(item for item in cap if "建筑绿色发展" in item["clause_path"])
    assert "最高贷款额度可进一步上浮" in green["content"]
    assert "同时符合多项条件" in green["content"]
    assert green["source_url"] and green["original_path"]
    tax = chunks(by_version["tax-2026-3"])
    same_city = next(item for item in tax if "同一城市范围" in item["clause_path"])
    assert "须同时满足以下条件" in same_city["content"]
    assert same_city["effective_to"] == "2027-12-31"
    assert same_city["effective_end_check"] == "first_clause_scope_machine_inferred_unverified"
    all_chunks = {part["chunk_id"]: part for item in files for part in chunks(item)}
    relate_versions(all_chunks)
    old_down = next(item for item in all_chunks.values() if item["version_id"] == "bj-housing-2025-360"
                    and item["policy_subject"] == "provident_second_down_payment")
    old_cap = next(item for item in all_chunks.values() if item["version_id"] == "bj-housing-2025-360"
                   and item["policy_subject"] == "provident_second_loan_cap")
    assert old_down["superseded_from"] == "2025-12-24"
    assert old_down["supersession_check"] == "machine_proposed_unverified"
    assert old_cap["superseded_from"] is None
    assert any(link["relation"] == "partial_overlap" for link in old_cap["version_relations"])


def test_clause_level_boundary_and_review_filter(tmp_path):
    store = PolicyStore(str(tmp_path / "qdrant"), model=TinyEmbedding())
    store.build()
    query = "北京公积金贷款二套住房最低首付款比例"
    def returned(day):
        return store.search(query, as_of=day, include_unreviewed=True, limit=10)["evidence"]
    for day in ("2025-08-09", "2025-12-23"):
        evidence = returned(day)
        assert any(item["version_id"] == "bj-housing-2025-360" and "30%" in item["content"]
                   for item in evidence)
        assert not any(item["version_id"] == "bj-housing-2025-565-bulletin" for item in evidence)
    on_change = returned("2025-12-24")
    assert any(item["version_id"] == "bj-housing-2025-565-bulletin" and "25%" in item["content"]
               for item in on_change)
    assert not any(item["version_id"] == "bj-housing-2025-360" and "30%" in item["content"]
                   for item in on_change)
    retained_cap = store.search("公积金二套住房最高贷款额度是多少", as_of="2025-12-24",
                                include_unreviewed=True, limit=10)
    assert any(item["version_id"] == "bj-housing-2025-360"
               and item["policy_subject"] == "provident_second_loan_cap"
               and "100万元" in item["content"] for item in retained_cap["evidence"])
    formal = store.search(query, as_of="2025-12-24", limit=10)
    assert any(item["version_id"] == "bj-housing-2025-565-bulletin" and "25%" in item["content"]
               for item in formal["evidence"])
    inner = store.search("非京籍五环内购房需缴纳几年社保", as_of="2026-08-08",
                         include_unreviewed=True, limit=10)
    assert any(item["version_id"] == "bj-housing-2026-400" and "1年及以上" in item["content"]
               for item in inner["evidence"])
    assert not any(item["version_id"] == "bj-housing-2025-565-bulletin"
                   and item["applicability_scope"].get("ring") == "inner" for item in inner["evidence"])
    before_new = store.search("非京籍五环内购房需缴纳几年社保", as_of="2026-08-07",
                              include_unreviewed=True, limit=10)
    assert any(item["version_id"] == "bj-housing-2025-565-bulletin" and "2年及以上" in item["content"]
               for item in before_new["evidence"])
    outer = store.search("非京籍五环外购房需缴纳几年社保", as_of="2026-08-08",
                         include_unreviewed=True, limit=10)
    assert any(item["version_id"] == "bj-housing-2025-565-bulletin" and "1年及以上" in item["content"]
               for item in outer["evidence"])
    broad_comparison = store.search("2026年8月前后五环内非京籍家庭购房条件是否有变化",
                                    include_unreviewed=True, limit=10)
    assert broad_comparison["evidence"]
    assert all(item["policy_subject"] == "nonlocal_purchase_social_years"
               and item["applicability_scope"].get("ring") == "inner"
               for item in broad_comparison["evidence"])
    both = store.search("公积金二套最高贷款额度夫妻双方均为缴存人", as_of="2026-08-08",
                        include_unreviewed=True, limit=10)
    assert any(item["version_id"] == "bj-housing-2026-400" and "200万元" in item["content"]
               for item in both["evidence"])
    assert not any(item["version_id"] == "bj-housing-2025-360" and item["policy_subject"] == "provident_second_loan_cap"
                   for item in both["evidence"])
    expired_condition = store.search("2028年换购住房退税须在同一城市吗", as_of="2028-01-01", limit=10)
    assert not any(item["version_id"] == "tax-2026-3" for item in expired_condition["evidence"])
    store.client.close()
