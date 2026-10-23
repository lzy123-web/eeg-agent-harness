"""Runtime EEG intent ontology used without offline evaluation gold."""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class AnalysisSemanticContract:
    analysis_type: str
    required_concepts: frozenset[str]
    optional_concepts: frozenset[str] = frozenset()

    def matches(self, concepts):
        concepts = frozenset(concepts)
        return (
            self.required_concepts <= concepts
            and concepts <= self.required_concepts | self.optional_concepts
        )


CONCEPT_ANCHORS = {
    "record_metadata": ("信息", "元数据", "采样率", "通道", "时长", "record info", "metadata"),
    "time_domain_amplitude": ("幅值", "振幅", "峰峰", "最大值", "最小值", "amplitude", "peak-to-peak"),
    "spectral_power": ("频带功率", "功率谱", "频谱", "绝对功率", "psd", "band power", "spectral power"),
    "event_locked": ("事件", "试次", "epoch", "event", "trigger"),
    "quality_measurement": ("质量", "噪声", "伪迹", "quality", "artifact", "noise"),
    "trial_selection": ("筛选", "筛除", "剔除", "选择试次", "trial selection", "reject trial"),
    "seizure_detection": ("癫痫", "发作", "seizure", "epilept"),
}


ANALYSIS_SEMANTIC_CONTRACTS = {
    item.analysis_type: item for item in (
        AnalysisSemanticContract("record_info", frozenset({"record_metadata"})),
        AnalysisSemanticContract("amplitude", frozenset({"time_domain_amplitude"})),
        AnalysisSemanticContract("psd", frozenset({"spectral_power"})),
        AnalysisSemanticContract(
            "event_workflow",
            frozenset({"event_locked"}),
            frozenset({"quality_measurement", "trial_selection", "spectral_power"}),
        ),
        AnalysisSemanticContract("record_quality", frozenset({"quality_measurement"})),
        AnalysisSemanticContract("seizure_detection", frozenset({"seizure_detection"})),
    )
}

EVENT_OBJECTIVE_CONCEPTS = {
    "quality_measurement": "epoch_quality",
    "trial_selection": "trial_selection",
    "spectral_power": "event_bandpower",
}


def selection_is_forbidden(forbidden_operations):
    for value in forbidden_operations:
        normalized = value.casefold().replace("-", "_").replace(" ", "_")
        if "selection" in normalized or "筛" in normalized or "reject_trial" in normalized:
            return True
    return False


def resolve_event_objectives(semantic_evidence, forbidden_operations=()):
    """Compose positive atomic objectives; a negated selection remains a prohibition."""

    concepts = frozenset(semantic_evidence)
    objectives = []
    for concept, objective in EVENT_OBJECTIVE_CONCEPTS.items():
        if concept not in concepts:
            continue
        if objective == "trial_selection" and selection_is_forbidden(forbidden_operations):
            continue
        objectives.append(objective)
    return tuple(objectives)


def concept_quote_is_grounded(concept, quote):
    """Check that an exact user span contains a declared concept anchor."""
    if concept not in CONCEPT_ANCHORS or not isinstance(quote, str):
        return False
    folded = quote.casefold()
    return any(anchor.casefold() in folded for anchor in CONCEPT_ANCHORS[concept])


def resolve_analysis_type(semantic_evidence: Mapping[str, str]):
    """Resolve a unique analysis capability from grounded semantic concepts."""
    matches = [
        name for name, contract in ANALYSIS_SEMANTIC_CONTRACTS.items()
        if contract.matches(semantic_evidence)
    ]
    return matches[0] if len(matches) == 1 else None

