---
name: task-tracker
description: Track tasks, deadlines, and follow-ups
triggers:
  - "add task"
  - "remind me"
  - "what's pending"
  - "todo"
---

# Task Tracker Skill

## What it does
Maintains a simple task list in a local markdown file.

## Storage
- File: workspace/tasks.md
- Format: markdown checklist with dates and priorities

## Commands
- "add task [description] by [date]" -> adds to list
- "what's pending" -> shows uncompleted tasks sorted by due date
- "done [task description]" -> marks as completed with timestamp
- "priorities" -> shows tasks sorted by priority (high/medium/low)

## Rules
- Auto-assign priority based on context (work > academic > personal)
- Warn if a task is overdue
- Include task count in daily briefing

## Model
- Use Haiku (simple file operations)
