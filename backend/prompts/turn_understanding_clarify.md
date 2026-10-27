User is answering the assistant's clarification from the prior turn. JSON only.

Set `clarification_choice` to one of: sell-in, sell-out, picking, unloading, or "" if free-text choice.
Set `pipeline_question` to the user's exact reply (short).
Always `is_conversational=false`, `attach_domain_catalog=false`, `referential_follow_up=false`.

Use `prior_question` and `assistant_clarification` in the payload—not keyword guessing.
