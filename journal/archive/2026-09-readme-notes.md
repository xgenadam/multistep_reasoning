# README narrative sections (archived verbatim, O-02)

From `README.md` at commit 236d168 ("TODO/caveats", "Results/thoughts"). O-05 rewrites the README.

## TODO/caveats
This project was mostly manually done, but I decided to let grok build loose on it to complete the final document oracle composition. This was mostly successful. The pain points came with the integration as an oobabooga extension. It seemed to be getting very bogged down into fetching the correct chat messages, implementing a now deleted scoring system which was sometimes responding to the wrong chat. Reading that was a massive wtf.

It also polluted the multi step reasoning with oobabooga specific code. The `reasoning_sub_agents` module should be all about the reasoning, and be platform agnostic.

I've fixed most of these, but I need to freshly test setting this up as an extension again.

Similarly it added mcp code to the `reasoning_sub_agents` module, but this should deffinitely live elsewhere and wrap that code.

I think there are also probably some cases where there is code that is unused, either introduced through multiple rounds through grok or as leftover from my own edits/deletions.

I'm on the fence about making this a propper package, currently it is only being tested/used as an extension package for oobabooga. However I want to make it more portable.
Early explorations of this via grok build as an MCP server did not result in what I was envisioning. As an MCP server that grok proposed, it would have required a dedicated LLM running as part of the server, however I envision this instead being a reasoning harness that the primary LLM can use. I need to think about how to implement this more (currently I am just exploring whether this reasoning harness results in improved responses).

While this does work, the final document does contain repetition. Currently we have the ability to add/delete/modify parts of a document, but I think we need to introduce the ability to merge and compare them to elimimate this.

Tool use inside the sub agents has not been implemented, and how tool use (such as search) gets handled is something I need to think about and experiment with.
I can see the benefits of each sub task agent being able to call tools, but if not handled appropriately it could become messy and complicated. 

## Results/thoughts

I've run this using Mistral 3.5 128B and Qwen 3.6 35B.
Obviously Mistral is much slower, for a single user input there are multiple calls to the LLM for each response, but it did provide better results in both cases.

For most use cases I think this does not need to be used, I would envision this being something the LLM can decide to use in the event it needs to ruminate more on a result before coming back with an immediate response.

As noted above, the final document does contain repetition, there are a few ways we can handle this, such as adding the ability to merge parts of the document, overhaul the entire thing etc. This needs experimentation to find what works best, and may be dependent on model competence itself.
