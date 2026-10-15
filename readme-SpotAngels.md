Company: SpotAngels

1. Solves one problem extremely well.
  Solves the problem of finding parking with a Waze-like app that directs to free parking and discounted parking.
2. You know the target customers or have direct access to them.
  The target customers are adults who drive somewhere and will need public parking. There are plenty of people like this at UVA.
3. You are familiar with (or can quickly learn) most of the required infrastructure.
   Yes, learning the infrastructure would be simple since the frontend is a webmap that communicates with a backend API for search locations, parking data, and applying filters.
   Beyond that there is a parking database for storing coordinates, rules, prices, restrictions, garages, etc. Overall, it follow the same architecture as other web apps.
5. Reimagines the problem space to make it significantly better.
  The problem space can be improved from being user driven to AI-driven by asking a user for specs such as desired commute, convenience, etc. and having an LLM find the best parking spot.
  This would replace the current flow of a user giving a destination and having to choose a parking spot themselves on a map. 
7. An LLM/Generative model is core to the solution (no generic "chatbot in a sidebar").
  The rework for this would be having an LLM at the core to take in user specs for their desired parking spot and then outputting a single spot instead of letting them choose.
8. Validation Guardrail: No LLM-generated artifact reaches the user without passing through a validator.
  A validator would ensure the chosen spot meets all inputted user specs. Another form of validation could be rerunning the model multiple times and making sure the output occurs a majority
  of the time. Essentially, if the model meets a certain threshold (the same parking spot is suggested 8/10 times) then that spot would be given to the user.
10. Self-Correction Loop: Validation errors must automatically feed back into the LLM to retry/correct.
  If we choose to check whether a LLM chosen parking spot meets all inputted user specs and it fails to meet even at least one then the model can be re-prompted to generate another suggestion.
11. Deployability: If built, you are able to fully deploy it.
  The current tool like any other web app is deployable so that same architecture would follow in the remodel. 
