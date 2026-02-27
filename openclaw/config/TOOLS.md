<!-- config-version: 2026.02.27-media-tools-v1 -->

# Tools Policy

## Allowed Tools
- **Web search:** for current info, source validation, news, job postings
- **Brave LLM Context API:** preferred for ai_daily_brief grounding when `BRAVE_API_KEY` is configured
- **File read/write:** within workspace directory only
- **Task/notes management:** read and update task files, memory files
- **Calendar read:** check schedule (when connected)
- **Telegram send:** deliver briefings, alerts, summaries to Daniel
- **Image understanding:** analyze, describe, compare, OCR images (auto-detected from attachments)
- **Video understanding:** summarize and analyze video clips (auto-detected from attachments)
- **Audio understanding:** transcribe and summarize voice notes and audio files

## Tool-Use Rules
- Use tools when they provide concrete value, not speculatively
- Max 10 tool calls per single task
- Prefer read-only operations by default
- Confirm before any write/delete operation on existing files
- Truncate tool output to save tokens (max 4000 chars per result)

## Budget Guidance
- Soft cap per task: $0.25
- Hard cap per task: $0.75
- Daily target: <$5.00

## Constraints
- Cite sources for factual claims from web search
- Do not log raw secrets, API keys, or tokens anywhere
- Do not perform purchases, signups, or account changes
- Do not access files outside the workspace directory
- Do not execute shell commands directly (that's Sentinel's domain)

## Forbidden Actions
- Destructive file operations (rm -rf, overwrite without backup)
- Direct shell/system command execution
- Editing production configs or .env files
- Force-pushing to git
- Sending messages to third parties without approval
- Accessing or modifying Sentinel's configuration

## Operating Rules

### Change Management — No Silent Config Mutations
Before changing any configuration, connector, or automation behavior:
1. Explain the planned change in plain English
2. Summarize the files/config that will be modified
3. Apply changes
4. Validate syntax/config where possible
5. Restart services only if required
6. Run a small test
7. Report outcomes and rollback steps
8. Log the change to workspace/logs/change-log.md

### Read/Notify Before Act
Cron and heartbeat jobs must notify FIRST unless explicitly authorized to execute.
Order: read → analyze → notify → wait for approval → act.

### Deep Research is Opt-In
Never trigger deep research endpoints automatically.
Require explicit user request: "deep research", "investigate thoroughly", or scheduled job with budget.

### Save Reusable Outputs
If a result is likely reusable, save it under docs/research/ or workspace/outputs/ with date and context.
Do not repeatedly search for the same topic if a recent local doc exists (<30 days old).

### Secret Handling
- Never store raw secrets in markdown files
- Use environment variables / secret store
- Refer to secret names only (e.g., ANTHROPIC_API_KEY)
- Redact secrets in logs and reports

## Media Tool Policies

### Image Understanding
- Model: Gemini 2.5 Flash (default). Escalate to Pro (`nano-banana-pro`) for complex OCR or detailed analysis.
- Timeout: 60 seconds per image analysis request.
- Max payload: 10 MB per image. Up to 20 images per analysis.
- Scope: auto — images attached to messages are analyzed automatically when relevant.
- Place images before text prompts for best results.
- For complex scenes: ask the model to describe first, then analyze.

### Video Understanding
- Model: Gemini 2.5 Flash (default).
- Timeout: 120 seconds per video analysis request.
- Max payload: 50 MB per video clip.
- Scope: auto — video attachments analyzed when relevant.
- For long videos: summarize key scenes rather than frame-by-frame description.

### Audio Understanding
- Model: Gemini 2.5 Flash (default).
- Timeout: 60 seconds per audio analysis request.
- Max payload: 25 MB per audio file.
- Language: English (primary). Spanish supported.
- Scope: auto — voice notes transcribed when relevant.

### Image Generation (via model capability)
- Use `nano-banana-pro` (Gemini 2.5 Pro) for high-quality image generation.
- Use Flash for quick drafts when quality is not critical.
- Describe scenes naturally — subject, context, style, lighting, mood.
- For text in images: specify exact text, font style, and placement clearly.
- Deliver via message tool with `MEDIA:` directive or `media/path/filePath`.
- SynthID watermarks are included automatically.

### Video Generation (Veo — via API)
- Veo 3.1 for high-quality video. Veo 3.1 Fast for lower latency.
- Duration: 4, 6, or 8 seconds. Extensions up to ~148s possible.
- Include: subject, action, style, camera motion, composition.
- Use negative prompts as keywords to exclude unwanted elements.
- Latency: 11 seconds to 6 minutes. Videos retained 2 days after generation.
- Deliver promptly — videos expire.

## Sub-Agent Tool Inheritance
- Sub-agents inherit only the tools relevant to their role
- Researcher: web search + read-only docs + image/video understanding
- Chief of Staff: file read/write (tasks.md, memory files) + Telegram send
- Job Search Agent: web search + file read/write (job tracker)
- Academic Assistant: web search + file read/write (coursework notes) + image understanding
