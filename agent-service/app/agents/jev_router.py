"""Independent TypeSafe System One client for bounded routing judgments.

Contract: https://docs.typesafe.ai/api (Choice and Noul answers).
"""

from __future__ import annotations

import json
from typing import Any, Literal
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


IntentChoice = Literal["listing_search", "aggregation", "ranking", "comparison", "trend", "data_quality", "unsupported", "clarify"]
ScopeChoice = Literal["current_listing", "active_import", "import_quality", "none"]

INTENT_CRITERIA = {
    "listing_search": "列出或筛选单条房源明细。",
    "aggregation": "在单个范围内求数量、均值、最大值或最小值等标量；某区最高月租是多少也属此类。",
    "ranking": "跨地区或群体排序、前 N 名、最高或最低的地区；单个范围求极值不属此类。",
    "comparison": "比较两个或多个地区或群体。",
    "trend": "要求多个自然月的序列、逐月统计或变化；即使指标是月度均价或数量也属此类。",
    "data_quality": "查询导入数据质量、有效记录、缺失、异常、重复或质量分；质量汇总中的行数也属此类。",
    "unsupported": "住房挂牌数据范围外，或要求写入、管理、预测、实际成交、政策。",
    "clarify": "缺少必要对象或指代上文但没有可用上文，例如单说'哪个更高'。",
}
SCOPE_CRITERIA = {
    "current_listing": (
        "默认口径：普通挂牌售房/出租房问数，包括明细、数量、均价、极值、按区排序和比较、"
        "按挂牌月份统计的趋势。平均、批量统计、多个月、历史挂牌日期都不自动改选导入数据集。"
    ),
    "active_import": (
        "仅当明确要求 Hive、离线/CSV 导入、当前激活的导入数据集、"
        "dataset_id、import_task_id、source_record_id 等导入记录时选择。"
        "普通挂牌统计或月度趋势本身不构成导入数据集要求。"
    ),
    "import_quality": "明确查询导入数据的质量汇总、有效记录、缺失、无效值、重复记录或质量分。",
    "none": "不应查询：预测或实际成交等未支持数据、政策等范围外问题、写入/删除操作，或无法理解查询任务。",
}

SCOPE_SOURCE = {
    "current_listing": "mysql", "active_import": "hive", "import_quality": "hive", "none": "none",
}
EXPLICIT_IMPORT_CRITERIA = {
    "yes": "问题明确点名 Hive/Hive 分析视图、当前已激活的离线或 CSV 导入数据集，或导入标识 dataset_id、import_task_id、source_record_id。",
    "no": "没有明确指定这些导入数据来源；普通挂牌问题，即使有均值、排名或月度趋势也选 no。",
}


class JevUnavailable(RuntimeError):
    pass


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["choice"]
    choice: str
    probabilities: dict[str, float]
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def check_distribution(self):
        if not self.probabilities or any(value < 0 or value > 1 for value in self.probabilities.values()):
            raise ValueError("invalid choice probabilities")
        if self.choice not in self.probabilities or abs(sum(self.probabilities.values()) - 1) > 0.02:
            raise ValueError("invalid choice distribution")
        return self


class NoulAnswer(BaseModel):
    type: Literal["noul"]
    noul: float = Field(ge=0, le=1)


class RouteSuggestion(BaseModel):
    intent: IntentChoice
    scope: ScopeChoice
    intent_confidence: float = Field(ge=0, le=1)
    scope_confidence: float = Field(ge=0, le=1)
    intent_probability: float = Field(ge=0, le=1)
    scope_probability: float = Field(ge=0, le=1)
    depends_probability: float = Field(ge=0, le=1)
    multiple_probability: float = Field(ge=0, le=1)
    explicit_import: bool = False
    explicit_import_probability: float = Field(default=0, ge=0, le=1)

    @property
    def requested_source(self) -> str:
        return SCOPE_SOURCE[self.scope]


def parse_route_response(payload: dict[str, Any]) -> RouteSuggestion:
    try:
        answers = payload["answers"]
        intent = ChoiceAnswer.model_validate(answers["intent"])
        scope = ChoiceAnswer.model_validate(answers["scope"])
        explicit_import = ChoiceAnswer.model_validate(answers["explicit_import"])
        depends = NoulAnswer.model_validate(answers["depends_on_previous"])
        multiple = NoulAnswer.model_validate(answers["multiple_tasks"])
        if (set(intent.probabilities) != set(INTENT_CRITERIA) or
                set(scope.probabilities) != set(SCOPE_CRITERIA) or
                set(explicit_import.probabilities) != set(EXPLICIT_IMPORT_CRITERIA)):
            raise ValueError("unexpected choice options")
        return RouteSuggestion(
            intent=intent.choice, scope=scope.choice,
            intent_confidence=intent.confidence, scope_confidence=scope.confidence,
            intent_probability=intent.probabilities[intent.choice],
            scope_probability=scope.probabilities[scope.choice],
            depends_probability=depends.noul, multiple_probability=multiple.noul,
            explicit_import=explicit_import.choice == "yes",
            explicit_import_probability=explicit_import.probabilities["yes"],
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise JevUnavailable("Invalid Jev routing response") from exc


class JevRoutingClient:
    def __init__(self, api_key: str, *, model: str = "jev-latest", timeout_seconds: float = 5.0,
                 endpoint: str = "https://api.typesafe.ai/v1/systemone") -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._endpoint = endpoint

    def classify(self, question: str, previous: dict[str, Any] | None, hive_available: bool) -> RouteSuggestion:
        state = {
            "current_question": question[:2000],
            "previous_structured_context": {
                key: (previous or {}).get(key) for key in
                ("cities", "districts", "metric", "listing_type", "intent", "pending_clarification")
            },
            "hive_available": hive_available,
        }
        body = {
            "model": self._model, "state": state,
            "questions": {
                "intent": {"type": "choice", "instructions": "判断唯一主任务。先排除不支持或无上文的省略问题，再区分质量、月度序列、比较、排名、明细和单值汇总；不生成 SQL。", "criteria": INTENT_CRITERIA},
                "scope": {"type": "choice", "instructions": "判断用户要求的数据集口径，不判断 Hive 当前是否可用，也不依据计算量选源。任务不支持或缺少上文无法确定时选 none；其它普通挂牌问题默认 current_listing。", "criteria": SCOPE_CRITERIA},
                "explicit_import": {"type": "choice", "instructions": "只判断当前问题是否明确指定导入/Hive 数据来源；不要依据计算类型推断。", "criteria": EXPLICIT_IMPORT_CRITERIA},
                "depends_on_previous": {"type": "noul", "instructions": "当前问题是否必须引用上一轮条件才能理解？完整的新问题或当前激活数据集算否。"},
                "multiple_tasks": {"type": "noul", "instructions": "当前问题是否要求两个独立查询？同一查询的多个字段或两地比较算否。"},
            },
        }
        request = Request(self._endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
            return parse_route_response(payload)
        except JevUnavailable:
            raise
        except Exception as exc:
            # Never include HTTP/SDK exception text: it may contain endpoint or credentials.
            raise JevUnavailable("Jev routing unavailable") from exc
