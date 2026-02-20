# Claude Code — How to Manage Long-Running Tasks

This is a personal reference for when Claude seems to be doing something forever and you don't know what's happening.

---

## The short answer: Ctrl+C to pause it — conversation stays intact

Press **Ctrl+C** at any time to immediately stop whatever Claude is doing.

**Ctrl+C does NOT restart the session. It does NOT lose your conversation.**
The history stays. The context stays. I still know everything we talked about.
After Ctrl+C you can just type: "what did you do so far?" and I'll tell you — then redirect me.

What DOES lose context:
- Closing the terminal window
- If you do close it by accident: `claude --continue` in terminal resumes the last session

---

## Key shortcuts

| What you want | Shortcut / Command |
|---|---|
| Stop Claude immediately | **Ctrl+C** |
| See what Claude is doing (verbose) | **Ctrl+O** |
| See task progress list | **Ctrl+T** |
| Move a bash command to background | **Ctrl+B** |
| Force Claude to plan before acting | **Shift+Tab** (toggles Plan Mode) |
| Check how much context is used | `/context` |
| Check token costs so far | `/cost` |
| Compress context to free space | `/compact` |
| Go back to a previous checkpoint | `/rewind` |

---

## When Claude is running for too long

1. **Press Ctrl+C** — stops the current action immediately. Conversation intact.
2. **Type "what did you do so far?"** — I'll summarize what I completed and what's pending.
3. **Redirect me** — e.g. "OK stop, just commit what you have" or "start over with just this one file."
4. **If you want to undo file changes**, run `/rewind` → pick a checkpoint → "Restore code and conversation".
5. **If the conversation is massive**, run `/compact focus on the certification fix` to shrink it before continuing.

---

## How to prevent this from happening

### Use Plan Mode first (Shift+Tab)

Before starting anything non-trivial, press **Shift+Tab** to enable Plan Mode. In this mode, Claude can only read files — it can't make changes. It shows you the plan and waits for your approval before doing anything. This avoids surprise 15-minute runs.

### Break up the task yourself

Instead of "fix the certifications issue", say:
- "Read resume_tailor.md and parsers.py and tell me what you think the fix should be." (read-only, fast)
- Then: "OK, now make those changes." (focused, short)

### Tell Claude to check in

Start your message with: **"Check in with me after each step before continuing."** Claude will pause between steps and wait for your go-ahead.

---

## The /compact vs /rewind difference

| Command | What it does | When to use it |
|---|---|---|
| `/compact` | Compresses conversation history to free context, keeps working | When context is getting full but work is not done |
| `/rewind` | Opens a checkpoint list to pick a point and revert | When you want to undo and try a different approach |

**If /compact seems to do nothing**: the context may not be full enough yet to trigger compression visibly, or you're already at a good size.

---

## See what's eating your tokens

Run `/context` — shows a visual grid of what's using context space. Run `/cost` — shows total tokens used this session.

Common culprits:
- Long tool outputs (file reads, bash results)
- MCP server overhead (check with `/mcp`)
- Claude reading many large files in one shot

---

## TL;DR

```
Task going too long?  → Ctrl+C to stop. Then ask "what did you do so far?"
Want to prevent it?  → Shift+Tab for Plan Mode before starting.
Want visibility?     → Ctrl+O for verbose. Ctrl+T for task list.
Want to undo?        → /rewind → pick checkpoint → restore.
Context too full?    → /compact to shrink it.
```
