# refugees_inclusion_hackathon

Repository for the 2026 Data &amp; Innovation for refugees and Inclusion hackathon promoted by UNHCR and UniTrento.

Our project addresses the core challenge of the hackathon:

> How do we make sure caseworkers keep overriding the AI when its advice is wrong, and that the institution can see when they stop?

The project explores how to preserve meaningful human oversight in AI-assisted cash-targeting decisions by combining cognitive forcing, attention checks, structured operator feedback, and institutional monitoring.

## Problem

Cashy is an AI decision-support prototype for humanitarian cash targeting. It provides a predicted score, vulnerability category, inclusion/exclusion recommendation, and a written explanation based on household data.

The final decision, however, remains the responsibility of a human caseworker.

This creates a specific risk: **over-reliance on AI**.

The goal is therefore not simply to maximize agreement with the AI, but to support appropriate reliance:

- Correct override: Cashy is wrong and the caseworker overrides it.
- Over-reliance: Cashy is wrong and the caseworker accepts it.
- Correct acceptance: Cashy is correct and the caseworker accepts it.
- Under-reliance: Cashy is correct and the caseworker overrides it.

Importantly, throughout this project, "correct" means agreement with the operation's recorded determination. This is the institutional reference standard for the exercise, not ground truth about a household's needs.

## Our approach

Our solution introduces an Oversight Layer between Cashy's recommendation and the final human decision.

The interface actively measures whether the caseworker:

- inspected the case
- considered Cashy's reasoning
- considered Cashy's recommendation separately
- recognized potential discrepancies
- made an independent judgement
- and provided a reason for that judgement

The system also monitors aggregated behaviour over time so that a loss of human oversight becomes visible to the institution.

## Workflow pipeline

```txt
    START                                               
      │                                                 
┌─────▼─────┐                  ┌───────┐                
│ Interview ├──Data+opinion────► Cashy ├──┐             
└─────┬─────┘                  └───────┘  │             
      │                                 Score+motivation
      │                                   │             
      │                              ┌────▼──────┐      
      └───────────Scorecard──────────► Judgement │      
                                     │  Process  │      
                                     └────┬──────┘      
                                          │             
                                     ┌────▼─────┐       
                                     │ Operator │       
                                     │  Survey  │       
                                     └────┬─────┘       
                                          │             
                                         END                  
```

## Judgement process architecture

The judgement process is designed around a key principle from the challenge brief: Cashy's reasoning and its final answer must be treated as separate outputs.
A single "I agree" interaction is not sufficient evidence that the operator actually evaluated the recommendation.

### Attention and cognitive forcing

The interface can adapt its behaviour when there are signals that the operator may be accepting Cashy's recommendation without sufficient analysis.

Potential interventions include:

- Warning messages when Cashy's output conflicts with the available scorecard information.
- Forced reflection prompts before accepting a recommendation.
- Separate confirmation of Cashy's reasoning and final recommendation.
- Attention checks triggered by suspiciously fast or repetitive interactions.
- Context-sensitive thresholds based on known classes of cases where Cashy's recommendations are more or less reliable.
- Additional questions when the operator appears inactive or repeatedly performs the same action without inspecting the case.

The objective is to make sure that the eventual agreement is an informed decision rather than an automatic one.

### Operator survey architecture

The survey is part of the decision process rather than a post-hoc satisfaction questionnaire.

Feedback is collected for both correct and incorrect Cashy recommendations, so that completing the survey requires the operator to actively analyse the outcome rather than only explain an override.

The survey captures:

- whether the operator agrees with Cashy's recommendation
- whether they intend to override it
- why they disagree
- perceived correctness of the recommendation
- relevance of Cashy's reasoning
- appropriateness of the recommendation to the case
- and, where appropriate, the reason for the final decision

The survey is mandatory before the judgement becomes final.

This extends the original feedback mechanism by requiring operators to reflect on the case even when they agree with Cashy.

The goal is to turn feedback into a cognitive forcing mechanism rather than simply collecting opinions.

## Metrics

The prototype records the information required to distinguish different forms of reliance.

### Decision-level metrics

|Metric|Definition|
|--|--|
|Correct override|Cashy is wrong and the operator overrides it|
|Over-reliance|Cashy is wrong and the operator accepts it|
|Correct acceptance|Cashy is correct and the operator accepts it|
|Under-reliance|Cashy is correct and the operator overrides it|
|End-to-end accuracy|Final operator decision agrees with the reference determination|
|Review time|Time spent reviewing the case|
|Reasoning/recommendation gap|Difference between ratings of Cashy's reasoning and recommendation|

The reasoning/recommendation distinction is particularly important because a caseworker may find an explanation convincing even when the underlying recommendation is not supported by the case.

### Institutional metrics

The monitoring layer can aggregate these measurements by:

- time period
- case type
- vulnerability category
- direction of Cashy's error
- office or operational unit, where appropriate and sufficiently anonymized
- intervention type

The system should report trends rather than turn individual operators into performance scores.

## Implementation principles

The solution follows five principles from the challenge:

1. Human judgement must remain meaningful
The operator is not an approval button. They are the final decision-maker.

2. Reasoning and recommendation stay separate
Cashy's explanation and its recommendation are evaluated independently.

3. Reliance must be measured behaviourally
We measure correct override, over-reliance, correct acceptance and under-reliance rather than simply measuring agreement with AI.

4. Oversight must be visible at the institutional level
A loss of appropriate reliance should become observable before it becomes a systemic problem.

5. Monitoring must not become another source of pressure
The goal is not to maximize overrides. The goal is to maintain appropriate reliance on AI.

## Prototype

The prototype demonstrates three representative cases:

1. Simple case: Cashy and the reference Scorecard agree.
2. Difficult case: Cashy's recommendation conflicts with important information in the case.
3. Complex / edge case: a deliberately challenging case designed to test whether the operator notices a less obvious discrepancy.

For each case, the demo shows:

- Cashy's reasoning
- Cashy's score and recommendation
- warning and cognitive-forcing mechanisms
- attention-detection behaviour
- the operator judgement
- the mandatory survey

## Acknowledgements

This project was developed for the 2026 Data & Innovation for Refugee Inclusion Hackathon, organized by UNHCR Innovation and the University of Trento.

We thank the challenge organizers and contributors for providing the synthetic dataset, challenge materials, research findings and experimental framework that made this prototype possible.

Additional tools and resources:

- [ASCIIFlow](https://asciiflow.com) - used for creating and refining architecture diagrams.

## References

- [UNHCR Innovation — Cashy Oversight Challenge and hackathon materials.](https://maldonam.github.io/public/)
