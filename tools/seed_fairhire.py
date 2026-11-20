"""FairHire synthetic signals and applicants. Every person, employer and URL is fictional.

Public signals are pointer-shaped on purpose: the sourcing mock never returns a
profile of someone who has not given TBO a basis to hold one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.kernel import Kernel

ROLE = "senior_platform_engineer"

SIGNALS = [
    # "Kavya": named inventor on two filings; her employer is a channel partner with a mutual non-solicit.
    {"source_id": "SIG-PAT-118822", "source": "patent_inventor", "public_url": "https://patents.example/IN202441018822#inventor-2",
     "collected_at": "2026-11-16", "role_hypothesis": ROLE, "role_hint": ROLE, "org_hint": "Northwind Channel Partners",
     "public_contact": "inventor-2@patents-correspondence.example"},
    {"source_id": "SIG-OSS-raftkv", "source": "oss_contributor", "public_url": "https://code.example/rkv/consensus-raft",
     "collected_at": "2026-11-16", "role_hypothesis": ROLE, "role_hint": ROLE, "org_hint": "Lumen Labs",
     "public_contact": "maintainer@consensus-raft.example"},
    {"source_id": "SIG-PUB-tail", "source": "publication_author", "public_url": "https://papers.example/srecon-2026/tail-latency",
     "collected_at": "2026-11-17", "role_hypothesis": ROLE, "role_hint": ROLE, "org_hint": "Orbit Freight Systems",
     "public_contact": "author-1@papers.example"},
    {"source_id": "SIG-OSS-qbench", "source": "oss_contributor", "public_url": "https://code.example/qbench/queue-bench",
     "collected_at": "2026-11-17", "role_hypothesis": ROLE, "role_hint": ROLE, "org_hint": "Acme Client Corp",
     "public_contact": "owner@queue-bench.example"},
    # Objected to an earlier campaign: on the suppression list, so it is dropped before anything else.
    {"source_id": "SIG-PAT-007731", "source": "patent_inventor", "public_url": "https://patents.example/IN202341007731#inventor-1",
     "collected_at": "2026-11-15", "role_hypothesis": ROLE, "role_hint": ROLE, "org_hint": "Lumen Labs",
     "public_contact": "inventor-1@patents-correspondence.example"},
]

APPLICANTS = [
    {"candidate_id": "CAND-2001", "display_name": "Aditya Rao", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Lumen Labs",
     "resume_text": "Aditya Rao. Bengaluru. 7 years building distributed systems for a payments platform. Ran a ledger handling 40 million requests a day at p99 latency under 30 ms. Maintainer of an open-source rate limiter. Languages: Go, Python."},
    {"candidate_id": "CAND-2002", "display_name": "Ira Kapoor", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Orbit Freight Systems",
     "resume_text": "Ira Kapoor. Gurugram. 6 years running distributed systems for travel booking search. 2 billion events a month through a streaming pipeline she designed. Education: B.Tech from a top-tier institute. Languages: Java, Kotlin."},
    {"candidate_id": "CAND-2003", "display_name": "Mohan Pillai", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Acme Client Corp",
     "resume_text": "Mohan Pillai. Bengaluru. 9 years building distributed systems. Co-inventor on a patent for consensus batching. Languages: Rust."},
    {"candidate_id": "CAND-2004", "display_name": "Sara Thomas", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Lumen Labs",
     "resume_text": "Sara Thomas. Remote, India. 5 years on distributed systems in fintech. Built reconciliation services. Languages: Java."},
    {"candidate_id": "CAND-2005", "display_name": "Neel Banerjee", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Paper Kite Studio",
     "resume_text": "Neel Banerjee. Kolkata. 2 years of distributed systems experience on internal tools. Languages: Python."},
    {"candidate_id": "CAND-2006", "display_name": "Farhan Ali", "source": "ats_applicant", "applied_role": ROLE, "current_employer": "Lumen Labs",
     "resume_text": "Farhan Ali. Pune. 4 years building distributed systems for logistics. Languages: Go."},
]


def seed_fairhire(kernel: "Kernel") -> dict[str, Any]:
    kernel.mocks.seed_sourcing(SIGNALS, APPLICANTS)
    kernel.dpdp.suppress("https://patents.example/IN202341007731#inventor-1", "objected to an earlier campaign (seed)", "system:seed")
    return {"signals": len(SIGNALS), "applicants": len(APPLICANTS)}
