"""Structured data types for the Consilium multi-agent system."""

from schemas.patient import PatientCase, MedicationHistory, VisitData
from schemas.responses import AgentResponse, Finding, Concern
from schemas.trace import ReasoningTrace, ConflictRecord, DebateRound
from schemas.output import FinalRecommendation, DrugOption, DrugAction
