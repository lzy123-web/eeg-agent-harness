"""Opt-in Agent adapters; frozen CIEDG classes remain unchanged."""

from ..integrated_method.transfer import ConstraintCarryingEEGAgentTransfer
from ..integrated_method.v11 import ConstraintCarryingEEGAgentV11
from .compiler import IntentCompilerV1Interpreter
from .scope import IntentScopeCompilerV2Interpreter


class IntentCompilerAgentV1(ConstraintCarryingEEGAgentV11):
    method_name = "ciedg_with_eeg_intent_compiler_v1"

    def __init__(self, llm_client, context, **kwargs):
        super().__init__(llm_client, context, **kwargs)
        self.interpreter = IntentCompilerV1Interpreter(llm_client)


class IntentCompilerTransferAgentV1(ConstraintCarryingEEGAgentTransfer):
    method_name = "ciedg_transfer_with_eeg_intent_compiler_v1"

    def __init__(self, llm_client, context, **kwargs):
        super().__init__(llm_client, context, **kwargs)
        self.interpreter = IntentCompilerV1Interpreter(llm_client)


class IntentScopeAgentV2(ConstraintCarryingEEGAgentV11):
    method_name = "ciedg_with_eeg_intent_scope_compiler_v2"

    def __init__(self, llm_client, context, **kwargs):
        super().__init__(llm_client, context, **kwargs)
        self.interpreter = IntentScopeCompilerV2Interpreter(llm_client)


class IntentScopeTransferAgentV2(ConstraintCarryingEEGAgentTransfer):
    method_name = "ciedg_transfer_with_eeg_intent_scope_compiler_v2"

    def __init__(self, llm_client, context, **kwargs):
        super().__init__(llm_client, context, **kwargs)
        self.interpreter = IntentScopeCompilerV2Interpreter(llm_client)
