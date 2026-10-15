Company: Relationship Hero

1. Solves one problem extremely well. 
  Provides an app to get expert advice for dating and relationships.

2. You know the target customers or have direct access to them.
   The target customers are adults who are dating or are in a relationship and would look for advice. There are plenty of people like this at UVA.

3. You are familiar with (or can quickly learn) most of the required infrastructure.
   The app does not require much difficult infrastructure considering the redesign we plan which would only require a conversation with a chatbot.

4. Reimagines the problem space to make it significantly better.
  Instead of needing to schedule an appointment with an expert and pay money, the user can ask an LLM trained on expert data to provide just as helpful advice and questions. Additionally, the LLM would allow the person to practice speaking with the person.
  
5. An LLM/Generative model is core to the solution (no generic "chatbot in a sidebar").
  The entire service would be based on an LLM since the user would be interacting with an input field which would be used to generate a prompt for an LLM which will return advice or act like a person in a dialogue.

6. Validation Guardrail: No LLM-generated artifact reaches the user without passing through a validator.
  The LLM response can be validated by first checking to make sure certain conditions are met like the correct format, or that certain words are not used, or that the sentiment is not negative or harmful.

7. Self-Correction Loop: Validation errors must automatically feed back into the LLM to retry/correct.
  The failed validation response can be regenerated until an appropriate response is given or at a certain limit a response can be given that the user should enter a different prompt.

8. Deployability: If built, you are able to fully deploy it.
  Only a web interface is needed for deployment, no physical elements.

