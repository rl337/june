# June Eval Research Brief

## Provenance and source synthesis

This brief was prompted by **Sër Makarevich's X post**:
https://x.com/sermakarevich/status/2106453816757354947

The post surfaced Anthropic's **“Demystifying evals for AI agents”** (published January 9, 2026):
https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

The Anthropic article is written by **Mikaela Grace, Jeremy Hadfield, Rodrigo Olivares, and Jiri De Jonghe**. Credit the X post as the discovery/provenance source and the Anthropic authors as the authors of the article; do not conflate those roles.

### Article conclusions to carry into the research

- Evals are core development infrastructure, not a test suite added after the agent is built.
- A useful agent eval distinguishes the **task**, repeated **trials**, one or more **graders/assertions**, the execution **transcript/trace**, and the actual environment **outcome**.
- Grade the real outcome whenever possible. An agent saying it succeeded is not evidence that the world reached the intended state.
- Prefer deterministic/code graders where the property is objectively checkable; use model graders for semantic or open-ended dimensions and calibrate them against humans.
- Avoid brittle path grading when several valid execution paths exist. Verify required constraints and outcomes rather than overfitting to one expected trajectory.
- Capability and reliability are different. `pass@k` asks whether success can be found across attempts; `pass^k` asks whether success repeats consistently.
- Capability suites should contain unsolved or partially solved work that provides a hill to climb. Once a capability is reliably solved, graduate it into regression coverage.
- Trials need clean, isolated environments so shared state or infrastructure noise does not masquerade as agent quality.
- Eval suites are living artifacts. Inspect traces, audit surprising failures, add real failures back as cases, watch for saturation, and keep graders resistant to loopholes.
- Held-out verification matters for self-improving agents: the signal used to guide improvement must not be the sole signal used to prove that improvement occurred.

## June research lens

For every reference below, the planning agent must record:

1. **Article-derived takeaway:** which conclusion above the reference strengthens, qualifies, or challenges.
2. **June semantic use:** the task contract, failure class, scenario, rubric, held-out check, or regression policy June should define.
3. **Research ask:** what the paper must resolve before that concrete eval is designed.
4. **MechaHarness requirement:** if the idea needs new lower-level machinery, specify only the generic interface/contract June needs.

The intended result is a concrete definition of “good” for June's real task families, while reusing MechaHarness for execution evidence, evaluator composition, trials, and verdict plumbing.

## Mission

Design June's **application-level evaluation system** on top of
MechaHarness evaluation primitives. June owns the meaning of success for
concrete tasks, the scenarios used to measure it, failure taxonomies,
regression/capability suites, and the evidence needed to decide whether
June is actually improving.

Assume MechaHarness can provide reusable
evidence/verdict/evaluator/trial primitives. If research reveals a
missing lower-level capability, record it as a **MechaHarness interface
requirement** rather than redesigning MechaHarness inside this plan.

## Questions to answer

1.  What does success mean for each major June task family?
2.  How should June construct capability, regression, reliability, and
    longitudinal-improvement suites?
3.  What failure taxonomy should June accumulate across task executions?
4.  How should open-ended tasks be graded when there is no single golden
    answer?
5.  How should June distinguish task success from conversational polish
    or self-reported success?
6.  How should June test whether memory/self-improvement actually
    transfers across related future tasks?
7.  Which evals may guide execution or improvement, and which must
    remain held out?
8.  What concrete evaluator capabilities must June request from
    MechaHarness?

## Primary research

### Stateful and longitudinal evaluation

-   **Continual Learning Bench: Evaluating Frontier AI Systems in
    Real-World Stateful Environments (CL-Bench)**\
    Permanent paper page: https://arxiv.org/abs/2606.05661\
    This is a core June reference. Study how it isolates improvement
    from baseline capability, uses related sequential tasks, and tests
    whether accumulated experience produces transferable gains rather
    than local overfitting.


    **Article-derived takeaway:** The article says evals should reveal whether changes genuinely improve an agent rather than merely move a score. CL-Bench extends that question across related tasks and accumulated experience.

    **Research ask:** Determine how to distinguish baseline capability from learning, measure transfer to later tasks, detect local overfitting, and construct held-out longitudinal scenarios.
-   **τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World
    Domains**\
    Permanent paper page: https://arxiv.org/abs/2406.12045\
    Study realistic tool-use tasks, domain rules, end-state
    verification, and `pass^k`. Translate these into June task suites
    and reliability requirements.


    **Article-derived takeaway:** The article emphasizes grading actual environment outcomes and uses `pass^k` to distinguish reliable agents from agents that merely succeed sometimes.

    **Research ask:** Extract patterns for isolated trials, end-state assertions, policy constraints, repeatability, and reliability aggregation that apply beyond the benchmark's specific domains.
-   **τ²-bench: Evaluating Conversational Agents in a Dual-Control
    Environment**\
    Permanent paper page: https://arxiv.org/abs/2506.07982\
    Study multi-party stateful workflows where both the user and agent
    can act. Use this to inform June evals for interactive workflows
    rather than treating the final response as the sole outcome.


    **Article-derived takeaway:** The article notes that interactive agents cannot be judged only from their final prose because both conversation and state transitions matter.

    **Research ask:** Determine how evaluation should represent two-sided actions, intermediate state, user simulation, valid alternate trajectories, and final outcome evidence.
### Open-ended and multidimensional grading

-   **GAUGE: Grading Agent-Built Financial Models Without a Golden
    Answer**\
    Permanent paper page: https://arxiv.org/abs/2607.24889\
    Study evaluation where multiple expert outputs can legitimately
    disagree. Focus on observed-practice envelopes, validity gates,
    auditable facets, and combining deterministic structure with
    judgment.


    **Article-derived takeaway:** The article says open-ended work needs multiple grading dimensions and human-calibrated semantic judgment. GAUGE is especially relevant where no single golden output exists.

    **Research ask:** Determine how validity gates, expert-practice envelopes, auditable facets, and deterministic structure checks can define acceptable outcomes without pretending there is one canonical answer.
-   **Ask, Don't Judge: Binary Questions for Interpretable LLM
    Evaluation and Self-Improvement (BINEVAL)**\
    Permanent paper page: https://arxiv.org/abs/2606.27226\
    Study decomposing broad quality rubrics into atomic questions that
    produce useful diagnostics and improvement signals.


    **Article-derived takeaway:** The article recommends clear, structured grading dimensions rather than one vague holistic judgment. BINEVAL pushes that idea toward atomic, interpretable claims.

    **Research ask:** Determine when a verdict should be represented as independently resolvable binary assertions, how uncertainty/unknown should propagate, and how those assertions compose without collapsing diagnostics into an opaque scalar.
-   **JudgeBench: A Benchmark for Evaluating LLM-Based Judges**\
    Permanent paper page: https://arxiv.org/abs/2410.12784\
    Use as a warning against treating an LLM judge as ground truth.
    Define how June will calibrate semantic graders and when
    human/domain-expert review is required.


    **Article-derived takeaway:** The article explicitly says model graders are non-deterministic and must be calibrated against human judgment. JudgeBench supplies the cautionary evidence for treating judges as fallible instruments.

    **Research ask:** Identify judge failure modes, calibration procedures, confidence/consensus strategies, and escalation conditions that should be represented in the eval design.
### Research and grounded-answer evaluation

-   **RAGAS: Automated Evaluation of Retrieval Augmented Generation**\
    Permanent paper page: https://arxiv.org/abs/2309.15217\
    Study context relevance, faithfulness/groundedness, and
    answer-quality dimensions as inspiration for June research/document
    tasks.


    **Article-derived takeaway:** The article's research-agent guidance decomposes quality into groundedness, coverage, source quality, and answer quality rather than asking one judge whether the answer is 'good'.

    **Research ask:** Determine which decomposed RAG dimensions transfer to agent evaluation, which require references, and how independent dimensions should be composed and diagnosed.
-   **ARES: An Automated Evaluation Framework for Retrieval-Augmented
    Generation Systems**\
    Permanent publication page:
    https://aclanthology.org/2024.naacl-long.20/\
    Study domain-adapted judges, small human-labelled calibration sets,
    confidence intervals, and separating retrieval quality from answer
    quality.


    **Article-derived takeaway:** The article recommends model graders only with calibration. ARES is relevant because it combines lightweight learned judges, human-labelled calibration, and statistical confidence.

    **Research ask:** Determine how small calibration sets, domain adaptation, confidence intervals, and specialized judges could fit a reusable escalation or application-level grading strategy.
-   **MiniCheck: Efficient Fact-Checking of LLMs on Grounding
    Documents**\
    Permanent publication page:
    https://aclanthology.org/2024.emnlp-main.499/\
    Study low-cost claim-grounding checks that June could request
    through generic MechaHarness evaluator interfaces.


    **Article-derived takeaway:** The article's deterministic-where-possible rule leaves a useful middle tier between code assertions and full generative judges: narrow, cheap learned verifiers.

    **Research ask:** Determine what evidence contract a specialized grounding checker needs, when it is trustworthy enough to stop escalation, and how its confidence should be recorded.
-   **SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection for
    Generative Large Language Models**\
    Permanent publication page:
    https://aclanthology.org/2023.emnlp-main.557/\
    Study consistency-based factuality signals, especially where June
    lacks a stable external reference answer.


    **Article-derived takeaway:** Repeated sampling can itself produce evidence when external ground truth is weak, but consistency is not the same thing as truth.

    **Research ask:** Determine where self-consistency is a useful auxiliary signal, how many samples are justified, and what safeguards keep agreement among generations from being mistaken for verified correctness.
### Suite design and measurement discipline

-   **Holistic Evaluation of Language Models (HELM)**\
    Permanent paper page: https://arxiv.org/abs/2211.09110\
    Study scenario taxonomies, multidimensional metrics, standardized
    conditions, and transparent reporting. Apply the idea to June task
    families rather than model leaderboards.


    **Article-derived takeaway:** The article argues against a single score and recommends suites that expose different dimensions, costs, and failure modes.

    **Research ask:** Identify which scenario/metric/reporting abstractions generalize cleanly to agent graphs and how raw evidence should remain inspectable beneath aggregates.
-   **Evaluating Large Language Models Trained on Code**\
    Permanent paper page: https://arxiv.org/abs/2107.03374\
    Foundational `pass@k` reference. Use it with τ-bench's `pass^k` so
    June explicitly separates "can eventually do it" from "does it
    reliably."


    **Article-derived takeaway:** The article uses `pass@k` to measure capability across attempts and contrasts it with `pass^k` reliability.

    **Research ask:** Pin down the statistical meaning and aggregation requirements of `pass@k`, then specify how it should coexist with reliability metrics without conflating 'can solve' with 'can be trusted'.
-   **The Verification Horizon: No Silver Bullet for Coding Agent
    Rewards**\
    Permanent paper page: https://arxiv.org/abs/2606.26300\
    Required shared reading. Apply it to June's self-improvement loop:
    the evaluator used to guide improvement must not be the only
    evaluator used to establish that improvement occurred.


    **Article-derived takeaway:** The article's warning about loopholes and grader bypasses becomes a first-class architectural concern: an evaluator can become a proxy target rather than a faithful measure of intent.

    **Research ask:** Determine how verification degrades as agents become more capable, which evaluators must be hidden/held out, and how evaluator versions and independent promotion checks should prevent self-improvement from merely learning the test.
## Concrete benchmark patterns

-   **SWE-bench: Can Language Models Resolve Real-World GitHub
    Issues?**\
    Permanent paper page: https://arxiv.org/abs/2310.06770\
    Use as an example of task instances with reproducible environments
    and concrete success conditions. Do not assume all June work can be
    reduced to binary tests.


    **Article-derived takeaway:** The article treats coding as the clearest example of grading the produced state with reproducible deterministic tests rather than trusting the agent's narration.

    **Research ask:** Extract benchmark-environment patterns for clean setup, outcome testing, regression protection, and separation between the agent harness and evaluation harness.
-   **Demystifying evals for AI agents**\
    Stable article page:
    https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents\
    Use its practical guidance for capability vs regression suites,
    balanced datasets, task clarity, grader calibration, transcript
    inspection, and long-term suite maintenance.

## Expected planning output

Produce a June implementation plan containing:

-   taxonomy of June task families;
-   success contracts for each task family;
-   initial failure taxonomy;
-   capability vs regression suite design;
-   repeated-trial reliability policy using `pass@k` and `pass^k`
    appropriately;
-   longitudinal/self-improvement evaluation inspired by CL-Bench;
-   research/document groundedness and source-quality evals;
-   open-ended rubric/facet design for tasks without a golden answer;
-   evaluator calibration and human-review strategy;
-   execution-visible vs held-out suite design;
-   eval dataset lifecycle and promotion of solved capability tasks into
    regression tests;
-   reporting of quality, reliability, latency, cost, and uncertainty
    without crushing everything into one scalar;
-   a section titled **Requirements on MechaHarness** listing only
    generic lower-layer capabilities June needs.

## Boundary rule

June owns concrete definitions of "good." MechaHarness owns the reusable
machinery for expressing and executing those definitions. When June
needs a new generic mechanism, specify its contract and push that
requirement downward; do not implement application semantics in the
harness layer.