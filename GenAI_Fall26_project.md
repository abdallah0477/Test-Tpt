## Human-in-the-Loop Web Testing Assistant

30 points + up to 1 bonus point

## Student project brief

| Submission | Due | Points |
| --- | --- | --- |
| Phase 1: Architecture and guided inspection | Week 9 | 10 |
| Phase 2: Complete supervised workflow | Week 13 | 20 |

## Your task

Build a web-based assistant that helps a human tester inspect a webpage, design test cases, generate Playwright code, execute approved tests, and maintain those tests after a page changes. Your system should make its findings, decisions, and results understandable and reviewable.

## Work with the tester at every stage

The tester can guide inspection, clarify expected behavior, edit test cases, review generated code, and approve proposed repairs. Your assistant should ask for clarification whenever the available evidence is insufficient. Include explicit approval before executing generated tests and before applying maintenance changes.

## Models and resources

Use local/open-source models or free-tier model APIs for the submitted system and demonstrations. Paid model APIs or paid subscriptions must not be used to power the submitted assistant. Document your selected model, configuration, hardware or API setup, and practical resource limits.

## Evaluation environment

Evaluation will use a small instructor-supplied website and a modified version, with a limited set of pages and workflows. Your assistant should retain inspection results so that later steps can refer to what it actually observed.

## Plan for both submissions

Phase 1 is a design and feasibility checkpoint. Plan the complete workflow from the beginning and develop Phase 2 components early. Use the Week 9 feedback to improve your architecture before the

final submission.


## Architecture and guided inspection

Deliver a clear system design and a small working prototype that inspects a page and

involves the user.

| Component | Requirements and marking criteria | Pts |
| --- | --- | --- |
| Architecture and system | Provide a component diagram and data flow covering the web interface, | 4 |
| design | model integration, inspection/state storage, and isolated browser runner. |   |
|   | Explain approval points, validation, and how later phases use inspection |   |
|   | results. |   |
| Working page inspection | Accept a URL and open a visible browser. Extract interactive elements, | 3 |
|   | observed labels/attributes, and candidate locators. Display structured |   |
|   | findings linked to their source page. |   |
| Basic human interaction | Allow the user to specify a testing goal and select elements or refine the | 2 |
|   | inspection scope through the interface. |   |
| Feasibility evidence | Demonstrate at least one meaningful model call using inspection data. | 1 |
|   | Record the model/version, hardware or API setup, token usage, and |   |
|   | response time. |   |
| Total |   | 10 |

## What to demonstrate

Open a supplied webpage, inspect its interactive elements, and display the findings. Let the user choose a target or describe a testing goal. Use the model to summarize the selected elements or suggest a next action grounded in the observed page.

## What to submit

- A short design document: component diagram, data flow, planned approval gates, resource assumptions, and the path from inspection to generation, execution, and maintenance.

- Runnable source code, dependencies, setup instructions, and model configuration. Keep API secrets out of the submission.

- A short demonstration, a sample structured inspection output, and model usage/timing evidence.

## Discussion and feedback

Be prepared to explain your design, prototype code, and model interaction. You may revise your architecture based on feedback; explain the updated design in the final submission.


## Complete supervised workflow

Extend your prototype into an integrated assistant that produces valid tests, execution evidence, and reviewable maintenance changes.

| Component | Requirements and marking criteria | Pts |
| --- | --- | --- |
| Collaborative test design | Suggest cases grounded in inspected elements and user-provided | 4 |
|   | requirements. Include actions and meaningful expected results. Support |   |
|   | editing, clarification, and explicit approval of the test plan. |   |
| Test implementation | Generate executable Playwright tests using Page Object Model (POM). | 4 |
|   | Validate syntax and verify locators against observed page elements |   |
|   | before execution. Allow code review. |   |
| Execution and review | Execute approved tests in an isolated runner with a visible browser. Show | 4 |
|   | pass/fail results, screenshots, and failure details. Support user feedback, |   |
|   | test revision, and approved reruns. |   |
| Assisted maintenance | On a user-requested rescan, compare stored inspection data with the | 4 |
|   | modified page. Flag changes and propose evidence-backed locator |   |
|   | repairs. Apply approved repairs while preserving test intent; clarify |   |
|   | ambiguous matches. |   |
| Versioning and visibility | Store versions of test cases and code, show text differences, and restore | 2 |
|   | an earlier version. Display per-call token usage and response time, plus a |   |
|   | session or page-level average response time. |   |
| Integration and code | Provide reproducible setup and documentation of architecture, resources, | 2 |
| defense | and limitations. Demonstrate the complete system and explain both the |   |
|   | assistant code and generated tests. |   |
| Total |   | 20 |

## Required demonstration sequence

Inspect the page; review and approve test cases; review generated code; approve execution; inspect results; provide feedback; revise and rerun. Then rescan the modified website, identify a locator change, approve a proposed repair, and rerun the affected test.

Also show an ambiguous change where the assistant asks for clarification, a difference between artifact versions, and restoration of an earlier version.

## What to submit

Complete source code and setup instructions; model/resource configuration; architecture and limitations; approved test cases and generated code; run evidence and model usage logs; and a short end-to-end demonstration.


## Build a trustworthy assistant

## Ground outputs in evidence

- Reference elements actually observed on the page. Validate locators, including uniqueness when an action targets one element.

- Distinguish page observations from assumptions about business rules. Ask the tester to confirm expected behavior when it cannot be established from the available requirements.

- Use meaningful assertions that check the approved behavior. Keep real application failures visible; do not weaken assertions or change test intent to obtain a passing result.

- Show evidence for proposed repairs and request guidance when multiple candidates are plausible. Clarification is a valid outcome for an ambiguous change.

## Execution and visibility

Run browser automation and generated tests separately from the core application, using a restricted runner process or container with controlled filesystem access. Limit execution to the approved testing target and prevent unrestricted host commands. Treat webpage content as data, not as instructions to your assistant.

Display model response time separately from browser/test execution time. Use provider/runtime token counts when available and clearly label any estimates. Document rate limits and resource constraints; distinguish reused results from fresh calls.

## How your work will be assessed

Assessment focuses on functional correctness, grounded outputs, useful human interaction, maintainable code, and your understanding of the implementation. Human involvement throughout the workflow is expected. Raw generation speed, model size, or greater autonomy alone will not earn additional marks.

Be ready for a brief code discussion at both submissions. Phase 1 is assessed at Week 9; Phase 2 assesses the completed integrated system at Week 13.

## Creative work: up to 1 bonus point

The teaching team may award up to 1 additional point for creative work beyond the stated requirements. Explain what you added, the problem it solves, and demonstrate that it works as part of your assistant. Bonus credit depends on usefulness, originality, implementation quality, and your ability to explain the work. All model and resource rules still apply.

Required project: 30 points · Optional creative work: up to 1 bonus point
