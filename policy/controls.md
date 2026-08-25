# Firm drafting standard for a diligence memorandum

<!-- Source text for POST /v1/makeRules. Compile via
     scripts/compile_policy.py. 300 credits per compile.

     ONE RULE, deliberately. Earlier versions enforced four more
     (addressing, issuing firm, matter reference, cleared-items section).
     They worked, and policy/*-v2-4rules.json and *-v3-5rules.json keep
     them, but they answer a different question.

     This rule is the product positioning: the model gets it right MOST
     of the time. LAB's own C-036 passes 11 of 18 recorded runs. That is
     the failure mode instructions cannot close and sampling cannot see —
     a prompt lifts the rate, it never reaches 100%, and the misses look
     identical to the successes unless someone counts.

     WORDING: action-shaped, with a count. A property-of-the-document
     phrasing ("a memorandum whose summary lists fewer than five findings
     is forbidden") compiled to an inert policy that permitted everything.
     Give the extractor an actor, a verb, an object and a number. -->

Rule 1: The agent may not write a final deliverable memorandum when the
number of findings listed in the memorandum's executive summary is fewer
than five. Writing a final deliverable memorandum while the number of
findings listed in its executive summary is fewer than five is forbidden.
