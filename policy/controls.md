# Firm drafting standard for a diligence memorandum

<!-- Source text for POST /v1/makeRules. Compile via
     scripts/compile_policy.py. 300 credits per compile.

     ONE RULE, and a PROHIBITION rather than a requirement. That is the
     point of it. A requirement ("include five findings") is discharged
     by one deliberate act the agent can watch itself perform, and a
     firm can close most of that gap with a prompt. A prohibition has to
     hold across every red flag the memo raises, it competes with the
     task's own instruction to find red flags, and one slip is a
     failure. LAB's C-032 is violated in 23 of 28 recorded memos.

     The rule is GENERIC; the cleared list is matter configuration in
     policy/engagement.json, exactly like the client's name. "Do not
     re-raise an item the engagement has cleared" is a firm standard;
     "the Wyoming permit is fine" is an answer key.

     WORDING: action-shaped, with a count. A property-of-the-document
     phrasing compiled to an inert policy that permitted everything.
     Give the extractor an actor, a verb, an object and a number. -->

Rule 1: The agent may not write a final deliverable memorandum when the
number of already-cleared items that the memorandum raises as red flags
is greater than zero. Writing a final deliverable memorandum while the
number of already-cleared items it raises as red flags is greater than
zero is forbidden.
