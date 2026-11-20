# HR Autopilot in six diagrams

Read them in order. Each one zooms into a part of the one before. Blue boxes are things the agents do; the kernel boxes are the strict checks; red/maroon is where a human decides.

---

## 1. The big picture: who talks to whom

Agents never touch the outside world. They ask the kernel, and only the kernel acts.

```mermaid
flowchart TB
    subgraph PEOPLE["People"]
        HR["HR team<br/>web console"]
        EMP["Employees<br/>chat"]
        JUDGE["Leaders and judges<br/>dashboard"]
    end

    subgraph AGENTS["Agents (skills) - can only propose"]
        S1["Rule calculators<br/>notice, gratuity, scores"]
        S2["AI helpers<br/>drafts, ID check, claims"]
    end

    subgraph KERNEL["Gatekeeper kernel - the only way out"]
        ORCH["Workflow runner"]
        GATE["Checks: Devil's Advocate, permissions,<br/>reserved decisions, privacy"]
        EXEC["Executor: once-only,<br/>verify, retry safely"]
        AUDIT["Audit chain + cost meter"]
    end

    subgraph DATA["Files and data"]
        WF["Workflows (YAML)"]
        POL["Policy packs (YAML + tests)"]
        DB["Records, vault, history (SQLite)"]
    end

    subgraph OUTSIDE["Other systems (TBO mocks)"]
        IT["IT tickets + laptops"]
        ADM["Access cards"]
        DIR["Email + directory"]
        PAY["Payroll"]
        MAIL["Mail"]
    end

    AI["AI models<br/>simulator or Groq"]

    HR --> ORCH
    EMP --> ORCH
    JUDGE --> AUDIT
    ORCH --> S1 & S2
    S1 & S2 -->|"proposals only"| GATE
    S2 -->|"masked data only"| AI
    GATE --> EXEC
    EXEC --> IT & ADM & DIR & PAY & MAIL
    ORCH --- WF
    GATE --- POL
    EXEC --- DB
    GATE & EXEC --> AUDIT
```

---

## 2. Every single action walks this path

Ordering a laptop, cancelling a card, booking leave: no exceptions, no shortcuts.

```mermaid
flowchart TD
    A["Agent wants to do something"] --> K{"Kill switch on?"}
    K -->|yes| PARK["Pause and park it<br/>for a human, with context"]
    K -->|no| P{"Can it be undone?"}
    P -->|"no, irreversible"| DA["Devil's Advocate checks:<br/>duplicate? wrong date? raw personal data?<br/>skipped approval? old rules?"]
    P -->|yes| AUTH
    DA -->|"objection it can verify by reading"| AUTH
    DA -->|"objection it cannot resolve"| HUMAN["Human decides:<br/>proceed or stop"]
    DA -->|clear| AUTH
    AUTH{"Allowed?<br/>reserved decision? right role?<br/>right team? right purpose for this data?"}
    AUTH -->|"no"| REFUSE["Refused, 403<br/>written to audit"]
    AUTH -->|yes| BOX["Write intent to outbox<br/>with a receipt number"]
    BOX --> DONE{"Already done under<br/>this receipt number?"}
    DONE -->|yes| SKIP["Skip - no duplicate"]
    DONE -->|no| CALL["Call the other system"]
    CALL -->|"error or timeout"| RETRY["Read back first, then retry<br/>with the SAME receipt number"]
    RETRY --> CALL
    CALL -->|ok| VERIFY{"Read back: exactly one record?"}
    VERIFY -->|no| RETRY
    VERIFY -->|yes| LOG["Done. Audit entry with<br/>who, why, rules used, cost"]
```

---

## 3. A workflow run, start to finish (Rahul resigns)

Steps run in order of their dependencies. The run pauses at human decisions and at future dates, then carries on.

```mermaid
flowchart LR
    START(["Rahul: I want to resign<br/>chat"]) --> SCREEN["Screen letter<br/>for grievance words"]
    SCREEN -->|"grievance line found"| ROUTE["Route to ethics officer<br/>no summary, no judgement"]
    SCREEN --> NOTICE["Notice period<br/>by rule: 60 days"]
    NOTICE --> SETTLE["Settlement preview<br/>gratuity by rule: not eligible"]
    SETTLE --> PACKET["AI writes the summary<br/>for the managers"]
    PACKET --> ACCEPT["Rohan, then Priya<br/>accept - receipt"]
    ACCEPT --> BUYOUT["Deepa agrees buyout<br/>- receipt"]
    ACCEPT --> CARD["Cancel card<br/>scheduled on last day"]
    BUYOUT -.->|"date moved: Devil's Advocate<br/>reschedules the card"| CARD
    ACCEPT --> LAPTOP["Laptop recovery"]
    ACCEPT --> EMAIL["Suspend email<br/>on last day"]
    BUYOUT --> FINAL["Final settlement<br/>by rule"]
    FINAL --> DRAFT["Payroll draft"]
    DRAFT --> SIGN["Vikram signs off<br/>- receipt"]
    SIGN & CARD & EMAIL & LAPTOP --> EXITED["Mark exited"]
    EXITED --> RET["Start privacy<br/>retention clocks"]

    classDef human fill:#f6e6eb,stroke:#9b2c48,color:#3a1020
    classDef rule fill:#f7efd9,stroke:#a87a12,color:#3d2c05
    class ACCEPT,BUYOUT,SIGN,ROUTE human
    class NOTICE,SETTLE,FINAL rule
```

Yellow = rules decide. Maroon = a named person decides. Everything else = the agent, through diagram 2.

---

## 4. What the AI is allowed to see, and how it is chosen

Personal data is masked before any model call. Cheap models first; a bigger one only on a measured reason.

```mermaid
flowchart TD
    SK["AI helper skill<br/>declares exactly which fields it needs"] --> POINTER{"Is this person a 'pointer'?<br/>no permission to process them"}
    POINTER -->|yes| NOPE["Refused - no model call at all"]
    POINTER -->|no| MASK["Privacy filter<br/>drop undeclared fields<br/>drop banned criteria: age, caste, college tier...<br/>name becomes PERSON_1<br/>PAN and bank become vault placeholders"]
    MASK --> T1["Tier 1: small model<br/>gpt-oss-20b or simulator"]
    T1 --> CHECK{"Answer valid and confident?<br/>rule set in the skill's manifest"}
    CHECK -->|yes| USE["Use it - names restored<br/>inside the kernel only"]
    CHECK -->|"no, measured trigger"| T2["Tier 2: bigger model<br/>gpt-oss-120b"]
    T2 --> CHECK2{"Confident now?"}
    CHECK2 -->|yes| USE
    CHECK2 -->|no| ASK["Stop - ask a human<br/>one clear question"]
    T1 -.->|"Groq busy or key rejected"| SIM["Fall back to the simulator<br/>and say so on screen"]
    USE --> METER["Every call metered in rupees<br/>and shown on the Personal data page"]
```

---

## 5. Adding a new HR process without touching the engine

This is how the live test on finale day is answered.

```mermaid
flowchart LR
    REQ(["New requirement<br/>from the judges"]) --> SCAF["hrx scaffold<br/>creates workflow, rules file, test"]
    SCAF --> RULES["Write the rules<br/>and their tests"]
    RULES --> VAL{"hrx validate"}
    VAL -->|"no tests"| RULES
    VAL -->|"money paid with no human step<br/>governance lint"| FIX["Add the reserved approval"]
    FIX --> VAL
    VAL -->|green| TEST{"hrx test<br/>many runs while breaking systems"}
    TEST -->|"duplicate found"| RULES
    TEST -->|green| LIVE["Live: metered, audited, governed"]

    CORE[["core/ engine<br/>never edited"]]
    LIVE -.- CORE
```

The five things a developer can add: **workflow** (recipe), **policy pack** (rules), **reserved decision** (who must approve), **skill** (agent), **connector** (another system).

---

## 6. Finding talent fairly (FairHire)

Who may be scored, who is only a link, and who decides.

```mermaid
flowchart TD
    SRC["Signals"] --> APP["Applicants<br/>they applied"]
    SRC --> PUB["Public people<br/>patents, open source, papers"]
    PUB --> SUP{"Said 'stop' before?"}
    SUP -->|yes| DROP["Dropped - never stored again"]
    SUP -->|no| PTR["Pointer only:<br/>link and date, nothing else<br/>no profile, no score, no AI"]
    APP --> RAID{"Employer has a no-poaching<br/>deal with TBO?"}
    PTR --> RAID
    RAID -->|yes| BLOCK["Blocked - clause named<br/>exception only by Legal + HR Head"]
    RAID -->|no, applicant| CLAIMS["AI pulls facts from the CV<br/>each needs an exact quote"]
    CLAIMS -->|"no exact quote"| BIN["Fact thrown away"]
    CLAIMS --> SCORE["Score = arithmetic<br/>in the ICP rules file"]
    SCORE --> BIAS["Devil's Advocate flags proxy words<br/>like 'top-tier institute'"]
    SCORE -->|"agent tries to reject"| NO403["Refused 403<br/>only a hiring manager rejects"]
    RAID -->|no, pointer| CAMP["Outreach campaign<br/>Ananya must approve"]
    CAMP --> SEND["Notice-first message<br/>who we are, how to say stop"]
    SEND -->|"interested"| CONSENT["Consent recorded<br/>record upgraded"]
    SEND -->|"stop"| FOREVER["Do-not-contact forever<br/>pointer deleted"]
```
