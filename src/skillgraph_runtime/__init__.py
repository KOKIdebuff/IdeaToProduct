"""Public Runtime Core API."""

from .domain import (
    CreateRunCommand,
    ExecutionPlan,
    FanOutExpansion,
    NodeAddress,
    RunSnapshot,
    SchedulingDecision,
    UsageRecord,
    ValidatedExecutorProposal,
)
from .errors import RuntimeContractError
from .kernel import RuntimeKernel
from .operations import RuntimeOperations
from .adapters import AdapterRegistry, FixtureAdapter, HostAgentAdapter, ManualAdapter
from .runtime_state import ExternalSubmission, ResultApplication
from .storage import RecoveryReport, StoredArtifact
from .idea_shaping import (
    AdaptiveIdeaShapingService,
    CallbackHostLLMProvider,
    ConservativeHostLLMProvider,
    FixtureHostLLMProvider,
    HostLLMProvider,
    IdeaSemanticRequest,
)
from .competitor_research import (
    CallbackCompetitorResearchProvider,
    CompetitorDeepDiveRequest,
    CompetitorDiscoveryRequest,
    CompetitorResearchProvider,
    CompetitorResearchService,
    ConservativeCompetitorResearchProvider,
    FixtureCompetitorResearchProvider,
)

__version__ = "0.2.0"

__all__ = [
    "RuntimeKernel",
    "RuntimeOperations",
    "AdapterRegistry",
    "FixtureAdapter",
    "ManualAdapter",
    "HostAgentAdapter",
    "CreateRunCommand",
    "RunSnapshot",
    "NodeAddress",
    "FanOutExpansion",
    "SchedulingDecision",
    "ExecutionPlan",
    "ValidatedExecutorProposal",
    "UsageRecord",
    "ResultApplication",
    "ExternalSubmission",
    "StoredArtifact",
    "RecoveryReport",
    "RuntimeContractError",
    "AdaptiveIdeaShapingService",
    "HostLLMProvider",
    "IdeaSemanticRequest",
    "CallbackHostLLMProvider",
    "FixtureHostLLMProvider",
    "ConservativeHostLLMProvider",
    "CompetitorResearchService",
    "CompetitorResearchProvider",
    "CompetitorDiscoveryRequest",
    "CompetitorDeepDiveRequest",
    "CallbackCompetitorResearchProvider",
    "FixtureCompetitorResearchProvider",
    "ConservativeCompetitorResearchProvider",
]
