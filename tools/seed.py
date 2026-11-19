"""Seed the synthetic dataset. SYNTHETIC DATA ONLY — every person here is fictional.

Identifiers are obviously synthetic: PANs start ``SYNPA``, bank accounts
``SYN-``, phones ``90000…``, emails at ``example.net`` / ``tbo-synthetic.example``.

Deterministic (seeded RNG, dates relative to the demo clock), so ``make bench``
reproduces the same numbers from the same commit.

    python -m tools.seed            # reset and seed var/setu.db + var/tbo_mocks.db
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.kernel import Kernel

FIRST = ["Aarav", "Ishita", "Kunal", "Nandini", "Siddharth", "Pooja", "Varun", "Aditi", "Rehan", "Kavya", "Manav", "Sneha",
         "Harsh", "Divya", "Omkar", "Ritika", "Yash", "Neha", "Arnav", "Shreya", "Dev", "Isha", "Kabir", "Lavanya"]
LAST = ["Sharma", "Nair", "Gupta", "Reddy", "Joshi", "Pillai", "Banerjee", "Kapoor", "Mishra", "Desai", "Chopra", "Menon",
        "Iyengar", "Saxena", "Bhat", "Ghosh", "Verma", "Kulkarni", "Patil", "Sinha"]
UNITS = {"ENG": ("engineering", "IN-KA"), "DATA": ("data", "IN-HR"), "PRODUCT": ("product", "IN-HR"),
         "FIN": ("finance", "IN-HR"), "SALES": ("sales", "IN-MH"), "OPS": ("operations", "IN-MH")}
TITLES = {"engineering": "Software Engineer", "data": "Data Analyst", "product": "Product Manager",
          "finance": "Finance Associate", "sales": "Account Manager", "operations": "Operations Associate"}
BASIC = {"L1": 28000, "L2": 36000, "L3": 52000, "L4": 78000, "L5": 92000, "L6": 140000, "L7": 210000}


def _pii(pan_digits: str, letter: str, n: int) -> dict[str, str]:
    pan = f"SYNPA{pan_digits}{letter}"
    return {
        "pan": pan,
        "identity_key": f"IK-{pan}",
        "bank_account": f"SYN-{n:08d}",
        "phone": f"90000{n:05d}"[:10],
        "personal_email": f"person{n}@example.net",
        "uan": f"SYNUAN{n:06d}",
        "date_of_birth": f"19{80 + n % 18}-0{1 + n % 9}-1{n % 9}",
    }


def seed(kernel: "Kernel", *, joiners: int = 8, leavers: int = 6) -> dict[str, Any]:
    rng = random.Random(42)
    today = date.fromisoformat(kernel.clock.today())
    sor = kernel.sor

    def emp(pid: str, name: str, unit: str, grade: str, *, doj: date, status: str = "active", extra: dict | None = None,
            pii_seed: int = 0, letter: str = "K") -> None:
        family, location = UNITS[unit]
        local = name.lower().replace(" ", ".")
        attrs = {
            "status": status, "grade": grade, "role_family": family, "role_title": TITLES[family], "location": location,
            "org_unit": unit, "employment_type": "permanent", "date_of_joining": doj.isoformat(),
            "basic_monthly": BASIC[grade], "contract_notice_days": None,
            "leave_balance": {"earned": float(rng.randint(4, 30)), "casual": float(rng.randint(1, 8)), "sick": float(rng.randint(3, 10))},
            "email": f"{local}@tbo-synthetic.example", "email_local": local, "manager_id": "EMP-2101", "manager_name": "Rohan Das",
            "buddy_id": "EMP-2207", "buddy_name": "Tanvi Kulkarni", "hrbp_id": "USR-101" if unit in ("ENG", "PRODUCT", "DATA") else "USR-108",
            "start_date": doj.isoformat(), "id_scan_quality": 0.95,
            "id_scan_text": f"GOVERNMENT PHOTO ID · NAME {name.upper()} · NO SYN-{pii_seed:06d} · ISSUED 2019",
        }
        attrs.update(extra or {})
        sor.create_person(pid, "employee", name, attrs, pii=_pii(f"{pii_seed % 10000:04d}", letter, pii_seed))
        sor.add_spell(f"SP-{pid}-1", pid, doj.isoformat(), attrs["employment_type"], grade)

    # ── the cast (DESIGN.md §4.3) ─────────────────────────────────────────────
    emp("EMP-2101", "Rohan Das", "ENG", "L6", doj=date(2019, 6, 3), pii_seed=2101)
    emp("EMP-2207", "Tanvi Kulkarni", "PRODUCT", "L4", doj=date(2021, 2, 15), pii_seed=2207)
    emp("EMP-3310", "Rahul Menon", "ENG", "L5", pii_seed=3310,
        doj=(today.replace(day=15) - timedelta(days=365 * 4 + 62)),     # ≈ 4 years 2 months of service
        extra={"leave_balance": {"earned": 21.0, "casual": 4.0, "sick": 7.0}, "basic_monthly": 92000})
    # Meera: joining in 11 days. Her faint ID scan goes to a human; her prior contract stint left an
    # allocation record open in the asset system (returned, never closed) — Prativaad's duplicate catch.
    emp("EMP-4821", "Meera Iyer", "DATA", "L4", status="pre_joining", pii_seed=4821, doj=today + timedelta(days=11),
        extra={"role_title": "Senior Analyst", "manager_id": "EMP-2101", "manager_name": "Arjun Mehta",
               "id_scan_quality": 0.42,
               "id_scan_text": "GOVERNMENT PHOTO ID · NAME MEERA IYER · NO SYN-0▒48▒▒ · ISSUED 20▒▒ (scan faint)"})
    sor.create_person("CAND-1182", "candidate", "Meera Iyer",
                      {"status": "closed_contract", "contract": "2024-03-01..2024-09-13", "note": "prior contractor stint"},
                      pii={"identity_key": "IK-SYNPA4821K"}, lawful_basis="voluntary_provision")

    # ── a realistic population ────────────────────────────────────────────────
    population = []
    for n in range(60):
        unit = rng.choice(list(UNITS))
        grade = rng.choice(["L2", "L3", "L3", "L4", "L4", "L5", "L6"])
        doj = today - timedelta(days=rng.randint(200, 3600))
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        pid = f"EMP-{5000 + n}"
        emp(pid, name, unit, grade, doj=doj, pii_seed=5000 + n, letter="Q")
        population.append(pid)

    # Pre-joiners for bench onboarding runs (good scans; one wants a band exception).
    for n in range(joiners):
        unit = rng.choice(list(UNITS))
        grade = rng.choice(["L2", "L3", "L4", "L5"])
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        emp(f"EMP-{6000 + n}", name, unit, grade, status="pre_joining", doj=today + timedelta(days=rng.randint(7, 21)),
            pii_seed=6000 + n, letter="J")

    # ── external systems ──────────────────────────────────────────────────────
    kernel.mocks.seed(prior_allocations=[{
        "allocation": {"serial": "LT-B907", "asset_class": "B", "holder_token": kernel.vault.token_of("identity_key", "IK-SYNPA4821K"),
                       "holder_ref": "CAND-1182"},
        "reference": "contract:CAND-1182:asset", "allocated_on": "2024-03-04T09:00:00+00:00", "returned_on": "2024-09-14"}])

    from tools.seed_parakh import seed_parakh  # the sourcing line seeds its own synthetic signals
    parakh = seed_parakh(kernel)
    return {"employees": 4 + 60 + joiners, "population_sample": population[:5], "parakh": parakh}


def reset_and_seed() -> dict[str, Any]:
    from core import config
    from core.kernel import Kernel

    for path in (config.db_path(), config.mocks_db_path()):
        for suffix in ("", "-wal", "-shm"):
            p = path.with_name(path.name + suffix)
            if p.exists():
                p.unlink()
    kernel = Kernel()
    return seed(kernel)


if __name__ == "__main__":
    print(reset_and_seed())
