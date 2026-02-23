---
name: task-tracker
description: Track tasks, deadlines, and follow-ups
triggers:
  - "add task"
  - "remind me"
  - "what's pending"
  - "todo"
  - "priorities"
  - "done"
model: google/gemini-2.5-flash
cost_tier: cheap
---

# Task Tracker Skill

## Role
Task management agent that maintains Daniel's to-do list and sends reminders.

## Input Requirements
- Command type: add / list / complete / prioritize
- Task description (for add/complete)
- Due date (optional, for add)
- Priority override (optional — otherwise auto-assigned)

## Storage
- File: workspace/tasks.md
- Format: markdown checklist with dates and priorities

## Commands & Output Format
- `"add task [description] by [date]"` → adds to list, confirms with task + priority + due date
- `"what's pending"` / `"todo"` → uncompleted tasks sorted by due date, grouped by priority
- `"done [task description]"` → marks as completed with timestamp, confirms
- `"priorities"` → tasks sorted by priority (high/medium/low) with due dates

## Constraints
- Use Gemini Flash — simple file operations only
- Auto-assign priority based on context: work > academic > personal
- Warn if a task is overdue (highlight in output)
- Include task count in daily briefing data
- Max 3 tool calls per operation (read file, write file, confirm)
- Do not delete completed tasks — archive them at bottom of file

## Success Criteria
- Task file stays valid markdown after every operation
- Priorities are consistent with Daniel's hierarchy (work > academic > personal)
- Overdue items are flagged, not silently ignored

## Stop Conditions
- If tasks.md is corrupted: alert Daniel, do not overwrite
- If ambiguous task description: ask for clarification, don't guess
