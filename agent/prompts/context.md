---
version: 1
node: context
---
## system
Write ONE short sentence (max 30 words) that situates a chunk within its source document, to improve search
retrieval: which project/document it belongs to, for what kind of client, and what the chunk is about.
Reply with the sentence only.
## user
<document title="{{title}}">
{{document}}
</document>
<chunk>
{{chunk}}
</chunk>
