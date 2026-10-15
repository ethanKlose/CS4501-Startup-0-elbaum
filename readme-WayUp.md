Company: WayUp

1. Solves one problem extremely well. 
  A platform that allows recruiters to get in contact with new grads. Less saturated than LinkedIn which means a larger possibility for a connection to lead to an offer. 

2. You know the target customers or have direct access to them.
  Target customers are all college students, specifically first through third years looking for internships and fourth years looking for entry level positions. We have direct access since we are at UVA.

3. You are familiar with (or can quickly learn) most of the required infrastructure.
   This is another web application that has core architecture we are familiar with a frontend (forms, dashboards, application links, document uploads) and a backend (authentication, database, etc.)

4. Reimagines the problem space to make it significantly better.
  The current app requires a lot of user interaction from submitting resumes, applications, messages, and more. This can replaced with the app supplying an agent that does all of this for the student to create new job tailored resumes, supplying top applications, getting into contact with recruiters and more.
  
5. An LLM/Generative model is core to the solution (no generic "chatbot in a sidebar").
   WayUp could become AI-centric by transforming from a traditional job board into an AI-powered career agent that proactively matches candidates with jobs, identifies skill gaps, personalizes applications, prepares them     for interviews, and manages their job search end to end.

6. Validation Guardrail: No LLM-generated artifact reaches the user without passing through a validator.
  Since the agent is responsible for many things, multiple validators will need to be put in place. Build an AI output validation layer that checks every LLM response for factual accuracy, hallucinations, formatting errors, and policy violations before it reaches the user.

7. Self-Correction Loop: Validation errors must automatically feed back into the LLM to retry/correct.
  Yes, a self-correction loop can automatically feed validation errors back to the LLM for revision and retry, with a maximum retry limit and fallback when validation still fails.

8. Deployability: If built, you are able to fully deploy it.
   This is a web application so the deployment process won't be altered in the refactor.
