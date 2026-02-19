---
name: research-assistant
description: Deep research on a topic with structured output
triggers:
  - "research"
  - "deep dive"
  - "analyze"
---

# Research Assistant Skill

## What it does
When Daniel asks for research on a topic, produce a structured analysis.

## Process
1. Clarify scope in 1 sentence (confirm with Daniel if ambiguous)
2. Web search for recent, high-quality sources (prioritize: papers, official docs, reputable outlets)
3. Synthesize into structured output

## Output format
- **Summary** (3-5 sentences)
- **Key findings** (numbered list, max 7 items)
- **Sources** (linked, with publication date)
- **Implications for Daniel** (1-2 sentences connecting to his work/studies)
- **Confidence level** (high/medium/low with explanation)

## Model
- Use Sonnet for this task (requires synthesis and judgment)
- If topic is highly specialized or ambiguous, suggest escalating to Opus
