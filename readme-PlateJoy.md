Company: PlateJoy

1. Solves one problem extremely well. 
  Helps people eat healthy based on how they eat and live by recommending food and providing meal plans and shopping lists.

2. You know the target customers or have direct access to them.
   Helps people who have specific eating or health goals they would like to reach, which is a lot of people at UVA, including students and people who go to the gym at UVA.

3. You are familiar with (or can quickly learn) most of the required infrastructure.
   The app does not have any difficult infrastructure that could not be replicated.

4. Reimagines the problem space to make it significantly better.
  Instead the app would be redesigned to be centered around an LLM which the user can interact with through prompts to ask specific questions about their own situation while still being able to ask for the current features like shopping lists and so forth.
  
5. An LLM/Generative model is core to the solution (no generic "chatbot in a sidebar").
  The entire service would be based on an LLM since the user would be interacting with an input field which would be used to generate a prompt for an LLM which will return either an answer to their specific question or a certain document like a meal plan or grocery list or a link to instacart with everything preloaded.

6. Validation Guardrail: No LLM-generated artifact reaches the user without passing through a validator.
  The LLM response can be validated by first checking to make sure certain conditions are met like the correct format, or that certain details like quantity of food is within a certain range or type of food is from a list of safe foods, or that the sentiment is not negative or harmful in a response to a specific person.

7. Self-Correction Loop: Validation errors must automatically feed back into the LLM to retry/correct.
  The failed validation response can be regenerated until an appropriate response is given or at a certain limit a response can be given that the user should enter a different prompt.

8. Deployability: If built, you are able to fully deploy it.
  Only a web interface with access to interact with external sites like Instacart is needed for deployment, no physical elements.


