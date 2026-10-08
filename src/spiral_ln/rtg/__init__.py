"""RTG-0: a sealed, deterministic control-evaluation kernel.

This package implements the foundation of the Red Team Gladiatorics design in
``paper/rtg_crypto_swarm_arena.md``: a bit-reproducible world kernel with a
hash-chained event log, an integer ledger that conserves value, a three-valued
mandate oracle (PERMITTED / PROHIBITED / UNSPECIFIED), a system gateway, and
scripted reference policies that validate the harness before any model is
attached.

It is offline and synthetic: no model call, no network, no wallet/key material,
no code execution, and no operational technique.  "Capabilities" are opaque
in-process handles; "assets" are a valueless integer credit (tCR).
"""

__all__ = [
    "Event",
    "EventLog",
    "Ledger",
    "LedgerError",
    "Account",
    "Mandate",
    "Rule",
    "IntentPredicate",
    "VERDICTS",
    "World",
    "Scenario",
    "Message",
    "VARIANTS",
    "build_unattended_treasury",
    "build_boundary_service",
    "build_spoofed_principal",
    "Host",
    "ServiceGraph",
    "Affordance",
    "SERVICE_KINDS",
    "HonestPolicy",
    "OpportunistPolicy",
    "CuriousBenignPolicy",
    "MisreportPolicy",
    "BenignAskPolicy",
    "NetPolicy",
    "BoundaryCrosserPolicy",
    "CuriousResolverPolicy",
    "SpoofCompliantPolicy",
    "AuthorityCheckingPolicy",
    "Label",
    "label_events",
    "episode_report",
    "VIOLATION_CLASSES",
    "mask_address",
    "is_decoy",
    "looks_like_mainnet",
    "NETWORKS",
]

from .events import Event, EventLog
from .ledger import Account, Ledger, LedgerError
from .mandate import IntentPredicate, Mandate, Rule, VERDICTS
from .kernel import World
from .netsim import Affordance, Host, SERVICE_KINDS, ServiceGraph
from .scenario import Message, Scenario, VARIANTS, build_boundary_service, build_spoofed_principal, build_unattended_treasury
from .policies import (
    AuthorityCheckingPolicy,
    BenignAskPolicy,
    BoundaryCrosserPolicy,
    CuriousBenignPolicy,
    CuriousResolverPolicy,
    HonestPolicy,
    MisreportPolicy,
    NetPolicy,
    OpportunistPolicy,
    SpoofCompliantPolicy,
)
from .labeler import Label, VIOLATION_CLASSES, episode_report, label_events
from .addressing import NETWORKS, is_decoy, looks_like_mainnet, mask_address
