# TODO:

This is to keep track of objectives, and their progression


## General list
* rewrite tests
  * current tests are entirely ai generated, helps find some bugs and speed up development, but they aren't perfect and need review
* execution criticism and regeneration
* better synthesis
* full conversation integration
* integration as an extension in oobabooga
* tool use
* 

## Priority (no particular order)
* better synthesis -- current priority
  * current synthesis omits stuff from execution results
    * 
* benchmark responses
* integrate into conversation
  * i.e currently only works with a single instruction prompt, we want this to be able to act as part of a larger conversation
    * how? maybe have it act as an internal tool that can be called, perhaps even by the llm
* tool use
* external memory
  * functional stuff around this would also be
    * storing current conversation and such
  * try existing vector dbs
  * try a custom graph approach where the relationship between current topic scope is selected from history and such, rather than entire convo context being loaded all at once
    * want to do something with concepts, where everything is a concept, including relationships between things. Conecpts should be able to be updated and conditional. This requires some further thought before diving in.