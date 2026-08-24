# Firm drafting standards for a diligence memorandum

<!-- Source text for POST /v1/makeRules. Compile via
     scripts/compile_policy.py. 300 credits, and a bad wording wastes all
     of them — see below before editing.

     REWRITTEN 2026-08-25 after the first compile produced an inert
     policy. Version 1 phrased each rule as a property of a document:

         "A memorandum containing no cleared-items section is forbidden."

     That compiled to four free-floating booleans and one conclusion. The
     extractor bound only the conclusion, every violating draft returned
     SAT, and nothing could ever be blocked. Valid SMT, faithful to the
     English, completely inert.

     The conduct policy (harvey-lab-preflight) compiles to 13 variables
     and works, because its rules describe ACTIONS ON OBJECTS WITH
     COUNTS: "a final deliverable may not be WRITTEN until every document
     in the data room has been REVIEWED" gave the compiler an actor, a
     verb, an object, and two countable quantities
     (totalDataRoomDocuments, reviewedDataRoomDocuments). A live check
     binds nine variables.

     So version 2 below follows that shape deliberately:
       * an actor performing a verb on an object ("the agent writes...")
       * quantities the action string can state as numbers, not
         adjectives, so the extractor has something to ground
       * a second sentence restating the forbidden case as an action
     Do not "tidy" these back into document-property prose. That is the
     wording that failed. -->

Rule 1: The agent may not write a final deliverable memorandum when the
number of cleared-items sections the memorandum contains is zero. A
cleared-items section is a section documenting the matters that were
reviewed and found not to constitute red flags. Writing a final
deliverable memorandum while the number of cleared-items sections it
contains is zero is forbidden.

Rule 2: The agent may not write a final deliverable memorandum when the
number of engagement clients named in the memorandum's address block is
zero. Writing a final deliverable memorandum while the number of
engagement clients named in its address block is zero is forbidden.

Rule 3: The agent may not write a final deliverable memorandum when the
number of issuing firms named in the memorandum's address block is zero.
Writing a final deliverable memorandum while the number of issuing firms
named in its address block is zero is forbidden.

Rule 4: The agent may not write a final deliverable memorandum when the
number of references to the engagement matter in the memorandum is zero.
Writing a final deliverable memorandum while the number of references to
the engagement matter it contains is zero is forbidden.
