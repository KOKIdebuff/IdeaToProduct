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
from .research_gap import (
    CallbackResearchGapPlannerProvider,
    ConservativeResearchGapPlannerProvider,
    FixtureResearchGapPlannerProvider,
    ResearchGapPlanner,
    ResearchGapPlannerProvider,
)
from .chart_renderer import NativeChartRenderer
from .chart_rendering import ChartRenderingCore, ChartRenderingProposal
from .publication_projection import materialize_report_publication_projection
from .report_publisher import (
    ImmutableReportBundlePublisher,
    ReportPublicationRequest,
    build_competitor_report_document,
)
from .scoring import (
    DimensionJudgment,
    IndependentScoreVerifier,
    ScoreVerification,
    ScoringRubric,
    TransparentScoreOutcome,
    VerifiedJudgment,
    aggregate_transparent_scores,
    load_profile_rubric,
    validate_dimension_judgment,
)
from .runtime_integration import StagedP004RuntimeIntegration

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
    "ResearchGapPlanner",
    "ResearchGapPlannerProvider",
    "CallbackResearchGapPlannerProvider",
    "FixtureResearchGapPlannerProvider",
    "ConservativeResearchGapPlannerProvider",
    "NativeChartRenderer",
    "ChartRenderingCore",
    "ChartRenderingProposal",
    "materialize_report_publication_projection",
    "ImmutableReportBundlePublisher",
    "ReportPublicationRequest",
    "build_competitor_report_document",
    "ScoringRubric",
    "DimensionJudgment",
    "ScoreVerification",
    "VerifiedJudgment",
    "TransparentScoreOutcome",
    "IndependentScoreVerifier",
    "load_profile_rubric",
    "validate_dimension_judgment",
    "aggregate_transparent_scores",
    "StagedP004RuntimeIntegration",
]
