# Product Requirements Document: AI Agent Task Manager

| | |
|---|---|
| **Product name (working)** | TaskFlow, AI Task Manager |
| **Document status** | Draft v1.3 for review (v1.1: board organised by status order, filter kept in the page address, due dates shown with year. v1.2: corner cases for dates, status reversal, limits and unsupported requests. v1.3: consistency fixes after cross-document review) |
| **Scope of this document** | Product behaviour only. Technology stack, database and architecture are deliberately excluded and will be covered in a separate technical design. |

---

## 1. Overview

### 1.1 Summary
TaskFlow is a single-page task manager that is controlled primarily through an AI chat assistant. The user types instructions in plain English, and the assistant understands them and carries out the task operations: create, list, edit, move, change status, complete, delete and search. The task board and the conversation are visible together on one page, so every instruction shows its result immediately.

### 1.2 Problem statement
Traditional task managers require users to navigate forms, dropdowns and menus for every small change. Users should be able to say what they want ("Move the demo task to In progress and mark the weekly report Done") and have it done correctly, safely and visibly.

### 1.3 Product positioning
The project is first an internship assignment, scoped to the provided specification. It is written so it could grow into a real product later, so a few forward-looking items are listed under Future Considerations (section 13).

---

## 2. Goals and Non-Goals

### 2.1 Goals
1. **Chat is the primary control.** Every core task operation can be completed by typing a message.
2. **Trustworthy actions.** Every instruction produces a clear success or error response. Ambiguous or destructive requests are clarified or confirmed before anything changes.
3. **Find tasks by meaning.** Users can find tasks with natural language (for example "tasks related to documentation"), not just exact keywords.
4. **Nothing is lost.** Tasks and chat history survive page refreshes and application restarts.
5. **One usable page.** The chat and the task list are always on the same page, on desktop and mobile.

### 2.2 Non-Goals
- User accounts, login, or multi-user collaboration
- Multilingual chat
- Teams, projects, sub-tasks, labels, attachments, recurring tasks, reminders or notifications
- Time-of-day on due dates
- Drag-and-drop reordering
- Answering general-knowledge questions unrelated to task management

---

## 3. Target User

**Primary persona: the individual planner.** A single person who keeps their own to-do list and prefers typing short instructions over clicking through forms. They are comfortable with a chat interface and want fast, low-friction task updates.

There is one user and no login. All tasks belong to that user.

---

## 4. Product Principles

- **Chat first, buttons optional.** Anything that can be done manually can also be done in chat. The reverse is not required.
- **Never guess on risky actions.** If a request could affect the wrong task, ask. If it deletes something, confirm.
- **Always say what happened.** Every response states what was done, what was found, or what went wrong, in plain language.
- **Single source of truth.** What the board shows is always the real, current state of the tasks.

---

## 5. Task Data Definition

Each task has the following user-visible attributes.

| Attribute | Required | Rules |
|---|---|---|
| **ID** | Auto | A stable, unique, deterministic identifier assigned at creation and never changed or reused. |
| **Title** | Yes | Short text. Must not be empty. |
| **Description** | No | Longer free text. |
| **Status** | Yes | One of: **To do**, **In progress**, **Done**. New tasks default to **To do**. |
| **Priority** | Yes | One of: **Low**, **Medium**, **High**. If the user gives no priority, it defaults to **Low**. |
| **Due date** | No | A calendar date (no time of day). Natural phrases are resolved to a real date in the user's local time zone. |
| **Completed time** | Auto | Recorded when a task becomes Done and cleared if it is reopened. Used to order the Done group (most recent first). |

### 5.1 Due date handling
- Phrases such as "today", "tomorrow", "Friday", "next week" and "in 3 days" are resolved to a specific date.
- The assistant always states the resolved date in its reply (for example, "due Wed 28 Oct 2026") so the user can verify it.
- If a date phrase cannot be resolved with confidence, the assistant asks the user instead of guessing.
- Dates in the past are accepted **only when the user states them explicitly** (for example "due 20 Oct 2026" or "due last Friday"). The assistant replies with the resolved date, notes that it is in the past, and the task shows as **Overdue** as soon as it is created. The same applies when the due date of an existing task is edited to a past date.
- Weekday names and phrases such as "Friday" or "next Monday" always resolve to the **next upcoming** matching day, never to a day that has passed. "Today" is never treated as past.
- A date given **without a year** (for example "12 Nov") resolves to the next upcoming occurrence of that date, and the reply states the full date with the year.
- A numeric date that can be read two ways (for example "03/04/2026") is never guessed. The assistant asks which day and month are meant.
- A date that does not exist (for example 30 Feb) is rejected with an explanation. A date more than one year ahead is confirmed with the user before it is saved ("Did you mean 12 Nov 2028?").
- A Done task is never shown as overdue. If it is reopened and its date has passed, it shows as Overdue again. Completing an overdue task removes the overdue flag.

### 5.2 Meaning of "move"
"Move" means changing a task's status (To do → In progress → Done). It does not mean reordering tasks within the list.

### 5.3 Status transitions
Any status can be changed to any other status. There is no fixed workflow and no step is blocked.

| From | To | Allowed | Notes |
|---|---|---|---|
| To do | In progress | Yes | Normal flow. |
| To do | Done | Yes | A step may be skipped. |
| In progress | Done | Yes | Normal flow. |
| In progress | To do | Yes | Step back. |
| **Done** | **In progress** | **Yes** | Reverses a completion. The completed time is cleared and the row leaves the Done group. |
| **Done** | **To do** | **Yes** | Same as above. This is also what the completion circle does when a Done task is clicked. |
| Same status | Same status | n/a | Reported as "no change needed", not as an error (FR-26). |

Rules:
- Becoming Done records a completed time. Leaving Done clears it. Completing again records a new time.
- Editing a Done task's title, description, priority or due date does not change its status.
- Status can be reversed from chat (to any status) and from the completion circle (to To do).
- Only deletion has an undo (optional). Every status change is reversed by simply changing the status again.

### 5.4 Field limits

| Field | Limit | If exceeded |
|---|---|---|
| Title | 200 characters, leading and trailing spaces removed | The assistant asks the user to shorten it. Nothing is saved. |
| Description | 1,000 characters | Same. |
| Chat message | 1,000 characters | Send is disabled until it is shortened. |

---

## 6. User Interface Requirements

The layout follows the supplied reference. Layout and colours may differ, but the elements below are required.

### 6.1 Page structure
- A single page with a header showing the product name, an "AI Task Manager" label, and a help (?) icon that opens a "What can I ask?" overlay with example prompts.
- **Task board** and **AI assistant panel** visible at the same time.
  - Desktop: side by side, with the task board on the left and the assistant on the right.
  - Mobile: stacked, with the task board on top and the chat input **pinned to the bottom** of the screen so it is always visible.

### 6.2 Task board (single list)
The board is one list. Each task row shows, as in the reference:

- A **completion circle** on the left (empty for open tasks, a check mark for Done)
- The **task title**
- A secondary line with the **due-date label and status** (for example "Tomorrow • To do", "Today • In progress", "Completed • Done")
- A **priority badge** on the right (High, Medium, Low), colour-coded
- **Done tasks** appear visually muted (greyed)

Additional board requirements:
- A **count badge** shows the number of tasks (for example "All tasks 6").
- The list is **organised into three status groups, always in this order: To do first, then In progress, then Done.** Each group has a header with its task count and can be collapsed (all groups are open by default).
- Within To do and In progress, tasks are sorted by due date (earliest first, no date last), then priority (High → Medium → Low), then oldest created first. Within Done, the most recently completed task comes first.
- Due-date labels use friendly wording: Today, Tomorrow, a weekday name (2–6 days ahead), and Next week (7–13 days ahead). Dates further away show the full date **with the year** (for example "12 Nov 2026"). Open tasks past their date show "Overdue • N days".
- Overdue open tasks are visibly flagged.
- When there are no tasks, the board shows an empty state that explains how to start (for example, "Try: Create a high-priority task to finish the demo tomorrow") and offers a **"Load sample tasks"** option.
- The description of a task is viewable (for example by expanding the row), even though it is not shown on the collapsed row.

### 6.3 Minimal manual controls
Chat is the primary control. Only two manual controls are provided:
- A **complete checkbox** (the completion circle) to mark a task Done or reopen it
- A **delete icon**, which asks for confirmation before deleting (a small dialog, as defined in the Screen Flow Document)

Manual changes use the same rules as chat changes and appear in the same source of truth.

### 6.4 AI assistant panel
- A header ("AI Assistant") with a short helper line ("Manage everything with a message").
- A scrolling **conversation area** with user messages and assistant replies visually distinct.
- A **message input field** and a **Send** button. Both are required. A placeholder example is shown (for example, "Type a task instruction…").
- Pressing Enter sends the message; Shift+Enter inserts a new line.
- A visible **loading indicator** while the assistant is working. The Send button is disabled while a request is in progress.
- A **"Clear chat"** control that removes the conversation history without touching tasks.
- When an assistant reply changes a task, the reply names the task and the change, and the changed row is briefly highlighted on the board.

### 6.5 Search and filter display
- After a search, the assistant lists the matches in chat **and** filters the task board to those matches.
- A visible **filter chip** (for example, "Filtered: documentation") shows the active filter, with a **"Show all"** option to clear it.
- A clean state is restored whenever the user clears the filter or runs an instruction that changes tasks outside the filter.
- The active filter (search phrase, status, priority, due range) is stored in the page address, so it survives a refresh and can be bookmarked or shared. Clearing the filter removes it from the address.

### 6.6 Responsiveness and accessibility
- Fully usable on common phone, tablet and desktop widths with no horizontal scrolling.
- Interactive elements are keyboard accessible, have visible focus states, and have text alternatives where icons are used.
- Colour is never the only way to convey priority or status (badges carry text labels).

---

## 7. Functional Requirements

Requirement IDs are used for traceability. Priority labels: **Must**, **Should**, **Could**.

### 7.1 Chat and instruction handling

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | The user can type a free-form English instruction and send it. | Must |
| FR-2 | The assistant interprets each message and determines which task operation(s) are requested. | Must |
| FR-3 | Every message receives a response that clearly states success, failure, a question, or a decline. | Must |
| FR-4 | A single message may contain **multiple actions** (for example, "Move the demo task to In progress and mark the weekly report Done"). Each action is handled independently. | Must |
| FR-5 | If some actions in a multi-action message fail, the valid ones are applied and the reply states exactly which succeeded, which failed, and why. | Must |
| FR-6 | Off-topic or unsupported requests are politely declined, with a short list of what the assistant can do. | Must |
| FR-7 | Chat history is **saved and restored** after a page refresh or application restart. | Must |
| FR-8 | The user can clear the chat history from the interface. Clearing chat never changes tasks. | Should |
| FR-9 | If the AI service is unavailable or fails, the chat shows a clear error and **no task is changed**. | Must |
| FR-10 | A typical instruction completes in **under 5 seconds**. | Should |

### 7.2 Task operations

| ID | Requirement | Priority |
|---|---|---|
| FR-11 | **Create:** the user can create a task from chat by giving at least a title. Description, priority and due date are optional. | Must |
| FR-12 | If no priority is stated on creation, the task is created with **Low** priority. If no status is stated, it is **To do**. | Must |
| FR-13 | **List:** the user can ask to see tasks, including by status, priority, due date, or topic (for example "Show all unfinished tasks related to documentation"). | Must |
| FR-14 | **Edit:** the user can change a task's title, description, priority or due date, and can clear an optional field such as the due date or description. | Must |
| FR-15 | **Move / change status:** the user can set a task to To do, In progress or Done. | Must |
| FR-16 | **Complete:** "complete", "finish" or "mark done" sets the status to Done. | Must |
| FR-17 | **Reopen / reverse a status:** the user can move a Done task back to To do or In progress, and can change any task to any other status (see 5.3). The completed time is cleared when a task leaves Done. | Must |
| FR-18 | **Delete:** the user can delete a task from chat, always subject to confirmation (see 7.4). | Must |
| FR-19 | The assistant never invents values. If a required value is missing or unclear (for example, a task title), it asks. | Must |
| FR-20 | Each task has a unique, stable ID that is never reused and that the assistant uses internally to act on the correct task. | Must |

### 7.3 Validation and error responses

| ID | Requirement | Priority |
|---|---|---|
| FR-21 | Invalid input is rejected with a clear explanation and an example of what is valid. Examples: empty title, unknown status, unknown priority, unparseable date. | Must |
| FR-22 | Statuses and priorities outside the allowed values are never stored. The assistant may map close wording to a valid value (for example, "urgent" → High, "in progress" or "started" → In progress) and states the mapping it applied. | Must |
| FR-23 | Responses distinguish clearly between **success** ("Done. I moved 'Finish AI presentation' to In progress."), **needs clarification**, and **error**. | Must |
| FR-24 | A request that refers to a task that does not exist produces a "not found" reply that offers the closest matches, if any. | Must |
| FR-25 | Before creating a task whose title closely matches an existing task, the assistant **warns and asks** whether to create it anyway. | Should |
| FR-26 | Setting a task to the state it is already in is reported as "no change needed", not as an error. | Should |

### 7.4 Ambiguity, confirmation and safety

| ID | Requirement | Priority |
|---|---|---|
| FR-27 | If a reference such as "the API task" matches more than one task, the assistant makes **no change** and asks a clarifying question with a **numbered list of candidates** (with title, status and due date). | Must |
| FR-28 | The user can resolve the ambiguity by replying with the number or by naming the task. The original instruction is then carried out. | Must |
| FR-29 | If the user does not resolve the ambiguity (for example, by changing the subject), the pending action is dropped and nothing changes. | Must |
| FR-30 | **Every delete requires explicit confirmation**, even when exactly one task matches. The confirmation message names the task being deleted. | Must |
| FR-31 | Filter-based **bulk actions** are supported (for example, "Mark all documentation tasks Done" or "Delete all completed tasks"). The assistant first shows a **preview of the affected tasks and their count** and waits for confirmation before applying. | Should |
| FR-32 | A confirmation can be cancelled, and cancellation leaves all tasks unchanged. | Must |
| FR-33 | **Undo** of the most recent delete is available shortly after deletion. | Could |

### 7.5 Semantic search

| ID | Requirement | Priority |
|---|---|---|
| FR-34 | The user can find tasks using natural-language descriptions that do not need to match the task's exact words (for example, "docs", "anything about the API", "stuff I need to present"). | Must |
| FR-35 | Search matches by **meaning** across the title and the description. | Must |
| FR-36 | Search can be combined with structured filters in the same sentence (for example, "unfinished" → status not Done; "high priority" → priority High; "due this week"). | Must |
| FR-37 | Results are ranked by relevance. Only results above a **relevance threshold** are returned. | Must |
| FR-38 | If nothing is sufficiently relevant, the assistant says that nothing matched. It does not show weak or unrelated tasks. | Must |
| FR-39 | Search results are shown in chat and as a filter on the board (see 6.5). | Must |
| FR-40 | Search results reflect the current state. A task created, edited or deleted is reflected in search immediately afterward. | Must |
| FR-41 | The same semantic matching is used to resolve vague task references in edit, move and delete commands (for example, "the demo task"), subject to the ambiguity rules in 7.4. | Must |

### 7.6 Persistence and consistency

| ID | Requirement | Priority |
|---|---|---|
| FR-42 | All task changes are saved and remain after a page refresh and after an application restart. | Must |
| FR-43 | Chat history remains after a page refresh and after an application restart. | Must |
| FR-44 | There is a single authoritative record of each task's state. The board and search results never disagree with it. | Must |
| FR-45 | If a change could not be saved, the user is told, and the board does not show it as saved. | Must |
| FR-46 | If two requests arrive in quick succession, they are processed in order and neither is silently lost. | Should |

### 7.7 Sample data

| ID | Requirement | Priority |
|---|---|---|
| FR-47 | The application starts with an **empty** task list. | Must |
| FR-48 | A **"Load sample tasks"** option adds the six sample tasks from the UI reference (Finish AI presentation, Review pull request #82, Send weekly report, Update API documentation, Set up database, Write project README). Loading is available from the empty state and does not create duplicates if used twice. | Should |
| FR-49 | The board is organised into three status groups, always in this order: **To do**, then **In progress**, then **Done**. | Must |
| FR-50 | Within each group, tasks are sorted by due date (no date last), then priority High → Medium → Low, then oldest created first. The Done group is sorted by most recently completed first. | Must |
| FR-51 | The active filter is stored in the page address so it survives a refresh and can be bookmarked or shared. | Must |
| FR-52 | A task can be created, or edited, with a past due date when the user states the date explicitly. The assistant notes that the date is in the past and the task shows as Overdue (see 5.1). | Must |
| FR-53 | Date interpretation follows 5.1: weekday names mean the next upcoming day, a missing year means the next upcoming occurrence, ambiguous numeric dates are asked about, impossible dates are rejected, and dates more than one year ahead are confirmed. | Must |
| FR-54 | Field limits in 5.4 are enforced. Over-limit input is never silently cut off. | Must |
| FR-55 | If an instruction is not understood, the assistant says so and gives examples. Greetings and "what can you do?" are answered with the list of capabilities. Read-only questions such as "how many tasks are overdue?" are answered with the number and an offer to show them. | Must |
| FR-56 | Task-related requests the product does not support (reordering, reminders, recurring tasks, copying, assigning, attachments) are declined with a short explanation of what is supported. Messages in a language other than English get a polite note that only English is supported. | Must |
| FR-57 | Duplicate-title checks ignore capitalisation and extra spaces, and also apply to titles repeated inside the same message. | Should |
| FR-58 | Relative due-date labels (Today, Tomorrow, Overdue) are recalculated whenever the calendar day changes while the page is open, and when the browser tab regains focus. | Must |
| FR-59 | "Load sample tasks" adds only the sample tasks that are missing. Their due dates are set relative to the day they are loaded. | Should |
| FR-60 | An instruction such as "delete everything" or "delete all tasks" is treated as a bulk delete. It shows the total count and requires a stronger confirmation. Words in a message that try to skip confirmation ("don't ask") are not honoured. Destructive actions always ask first. If bulk actions are not built in a release, "delete everything" is declined with an explanation instead of being carried out. | Must |

---

## 8. User Stories and Acceptance Criteria

### Story 1: Create a task
*As a user, I want to create a task by typing it, so I don't need a form.*

- **Given** I type "Create a high-priority task to finish the demo tomorrow", **when** I send it, **then** a task titled along the lines of "Finish the demo" appears on the board with priority High, status To do, and tomorrow's date as due date.
- The reply confirms the title, priority, status, and the resolved due date.
- **Given** I type "Add a task: buy printer paper", **then** the task is created with priority **Low**, status To do, and no due date.
- **Given** I type "Create a task" with no title, **then** the assistant asks what the task should be called, and no task is created.

### Story 2: List and filter tasks
*As a user, I want to see tasks that match certain conditions.*

- **Given** I type "Show all unfinished tasks related to documentation", **then** the reply lists only tasks that are To do or In progress and semantically related to documentation, and the board is filtered to those tasks with a visible filter chip.
- **Given** nothing matches, **then** the reply says no matching tasks were found and the board is not emptied of unrelated tasks.
- **Given** I click "Show all" on the filter chip, **then** all tasks are shown again.

### Story 3: Change status (multi-action)
*As a user, I want to update several tasks in one message.*

- **Given** I type "Move the demo task to In progress and mark the weekly report Done", **then** each task is updated and the reply confirms each action separately.
- **Given** the weekly report task does not exist, **then** the demo task is still moved, and the reply states that the weekly report could not be found.

### Story 4: Edit a task
*As a user, I want to change task details naturally.*

- **Given** I type "Change the priority of the API task to Low" and exactly one task matches, **then** its priority becomes Low and the reply confirms the change.
- **Given** two tasks match "API", **then** nothing changes and the assistant shows a numbered list and asks which one I mean.
- **Given** I reply "2", **then** the second candidate is changed and the reply confirms it.
- **Given** I type "Remove the due date from the demo task", **then** the due date is cleared.

### Story 5: Delete a task
*As a user, I want to delete tasks safely.*

- **Given** I type "Delete the README task" and one task matches, **then** the assistant asks "Delete 'Write project README'? (yes/no)" and does nothing until I answer.
- **Given** I answer "yes", **then** the task is removed and the reply confirms it.
- **Given** I answer "no" or change the subject, **then** the task remains.

### Story 6: Bulk action
*As a user, I want to update many tasks at once without risk.*

- **Given** I type "Mark all documentation tasks Done", **then** the assistant lists the affected tasks and the count and asks for confirmation before changing anything.

### Story 7: Persistence
*As a user, I want my work to still be there tomorrow.*

- **Given** I have tasks and a chat conversation, **when** I refresh the page or restart the application, **then** all tasks and the full conversation are still present and identical.

### Story 8: Safe failure
*As a user, I want clear feedback when something goes wrong.*

- **Given** the AI service cannot be reached, **then** the chat shows an error such as "I couldn't process that right now. No changes were made." and no task changes.
- **Given** I type "Set the demo task to Urgent-ish status", **then** the assistant explains the valid statuses and does not change the task.

### Story 9: Off-topic requests
- **Given** I type "What's the capital of France?", **then** the assistant politely explains it manages tasks and lists a few things it can do.

### Story 10: Past and unusual due dates
*As a user, I want to record tasks that are already late, and I want dates read correctly.*

- **Given** today is 27 Oct 2026 and I type "Create a task to file taxes due 20 Oct 2026", **then** the task is created in To do with that date, the reply notes the date is in the past, and the row shows "Overdue • 7 days".
- **Given** I type "Create a task due Friday", **then** the due date is the next upcoming Friday, never a past one.
- **Given** I type "Create a task due 12 Nov", **then** the reply states the full date "Thu 12 Nov 2026".
- **Given** I type "due 03/04/2026", **then** the assistant asks whether I mean 3 April or 4 March and creates nothing until I answer.
- **Given** I type "due 30 Feb", **then** the assistant says it is not a real date and asks again.
- **Given** I edit an existing task's due date to a past date, **then** the same rules apply.

### Story 11: Reversing a status
*As a user, I want to undo a completion or step a task back.*

- **Given** "Set up database" is Done and I type "Move the database task back to In progress", **then** it leaves the Done group, appears in In progress, is no longer greyed out, its completed time is cleared, and the reply confirms.
- **Given** I click the check mark on a Done task, **then** it returns to To do.
- **Given** a task is To do and I type "Mark the demo task Done", **then** it moves straight to Done.
- **Given** a Done task's due date has passed and I reopen it, **then** it shows as Overdue.

---

## 9. Assistant Behaviour and Tone

- Concise, friendly, and plain-language. No technical jargon in replies.
- Reply format for changes: state the action taken, the task name, and the new value ("Done. I moved 'Finish AI presentation' to In progress.").
- Replies for questions end with a clear question and a short way to answer (for example, "Reply with 1 or 2").
- The assistant never claims an action was done unless it actually was.
- English only.

### 9.1 Supported intents (for reference)
Create task, list/show tasks, search tasks, edit task, change status/move, complete, reopen, delete, bulk update, bulk delete, undo (stretch), help/capabilities.

---

## 10. Edge Cases

| Situation | Expected behaviour |
|---|---|
| Empty or whitespace-only message | Send is disabled or the message is ignored, with no assistant call. |
| Very long message or pasted text | The assistant handles it, or states a clear length limit. |
| Message contains multiple tasks to create ("Add tasks: A, B and C") | Each is created and the reply lists all of them. |
| Same title already exists | The assistant warns and asks whether to create another (FR-25). |
| Task reference matches nothing | "Not found" reply, with closest matches if any. |
| Task reference matches several | Clarify before any change (FR-27). |
| User references a task by position ("the second one") | Resolved against the most recently shown list if there is one; otherwise the assistant asks. |
| Pronouns and follow-ups ("mark it done", "make that high priority") | Resolved against the task most recently discussed; if unclear, the assistant asks. |
| Pending confirmation, then the user sends an unrelated instruction | The pending action is cancelled and the new instruction is handled. |
| Past due date | Accepted when explicit; the assistant notes it is in the past. |
| Ambiguous date ("next Friday", "end of month") | The assistant states the date it resolved to, or asks if unsure. |
| Conflicting instruction ("mark Done and delete") | The assistant asks for clarification. |
| Quick repeated sends | Requests are processed in order; Send is disabled during processing. |
| Page refreshed mid-request | After reload, the user sees the saved state and can re-send if the action did not finish. |
| Completed task edited | Allowed; the status stays Done unless changed. |
| Many tasks (hundreds) | The board and search remain usable and responsive. |
| Special characters, emoji, quotes in titles | Stored and displayed correctly. |
| Create a task with a past due date | Accepted when stated explicitly. The reply notes it is in the past. The task appears in To do as Overdue. |
| Edit a due date to a past date | Same as above. |
| Move a Done task back to In progress or To do | Allowed. Completed time cleared. The row moves to the new group and the reply confirms. |
| Move a To do task straight to Done | Allowed. |
| Reopen a Done task whose due date has passed | Returns as Overdue. |
| Complete an overdue task | The overdue flag is removed. |
| Date with no year | The next upcoming occurrence is used and the year is stated. |
| Ambiguous numeric date (03/04/2026) | The assistant asks which reading is meant. |
| Date that does not exist (30 Feb) | Rejected with an explanation. |
| Date more than one year ahead | The assistant asks the user to confirm. |
| Title or description over the limit | The assistant asks to shorten it. Nothing is saved. |
| Rename a task to an empty title | Rejected. The old title is kept. |
| Midnight passes while the page is open | Labels are recalculated: Tomorrow becomes Today, and today's tasks become Overdue the next day. |
| "Delete everything" or "delete all tasks" | Bulk delete with the total count and stronger confirmation. |
| Message in another language | A polite note that only English is supported. |
| Greeting, gibberish, or "what can you do?" | A friendly reply that lists what the assistant can do, with examples. |
| Unsupported request (reorder, reminders, recurring, copy, assign) | Declined, with what is supported instead. |
| A task title that sounds like a command ("Create a task: delete old files") | Treated as a title. Nothing is deleted. |
| Same instruction sent twice ("Mark the report Done" twice) | Second reply: "already Done. No change needed." |
| Bulk status change that includes Done tasks | The preview lists them and says how many are Done. |
| Last remaining task deleted | The empty state appears again. |
| Task moved out of the active filter | It leaves the filtered board and the reply explains, with "Show all". |
| Load sample tasks after deleting some | Only the missing sample tasks are added. |
| Same title twice in one message | The second is flagged as a possible duplicate before it is created. |
| Clear chat or Load sample tasks while a request is running | Both controls are disabled until the reply arrives. |

---

## 11. Non-Functional Requirements

| Area | Requirement |
|---|---|
| **Performance** | A typical chat command completes in under 5 seconds. The board updates immediately after a successful action. Page load is fast on a standard connection. On free hosting, the first visit after a quiet period can take up to about a minute; the page explains the wait with a "waking up" message (Screen Flow LD-08). |
| **Reliability** | Tasks are never lost on refresh or restart. Failed requests never leave a task half-changed. |
| **Accuracy** | Semantic search returns relevant tasks and avoids irrelevant ones (see success metrics). Actions apply to the intended task. |
| **Data integrity** | One authoritative state per task; deterministic, never-reused IDs. |
| **Usability** | A new user can complete the first task creation without instructions. |
| **Responsiveness** | Works on phone, tablet and desktop; chat input always visible. |
| **Accessibility** | Keyboard operable, visible focus, text labels for status and priority. |
| **Privacy** | Single user, no sign-in. Anyone who has the app's address can see and change the tasks, so the address should be treated as private. Task text is sent to the AI provider only as needed to process instructions. |
| **Observability** | Failed or unrecognised instructions are recorded so they can be reviewed and the assistant improved. |

---

## 12. Success Metrics

These are measured on a set of test prompts prepared before release.

| Metric | Target |
|---|---|
| Instructions correctly understood and executed (create, list, edit, move, complete, delete) on the test set | ≥ 90% |
| Ambiguous task references that trigger a clarification instead of a change | 100% |
| Deletes executed without confirmation | 0 |
| Semantic search: relevant tasks appear in results for natural-language queries (recall on the test set) | ≥ 85% |
| Semantic search: unrelated tasks shown in results (false positives) | ≤ 10% |
| Failed requests that change task state | 0 |
| Tasks and chat preserved after refresh and restart | 100% |
| Typical command response time | < 5 seconds |
| Every response clearly labelled as success, question or error | 100% |

---

## 13. Future Considerations (Out of Scope for v1)

- User accounts and private per-user task lists
- Multiple languages
- Kanban board view or a list/kanban toggle
- Due times, reminders and notifications
- Recurring tasks, sub-tasks, labels, projects
- Voice input
- Fallback keyword commands when the AI service is down
- Manual full-edit forms, drag-and-drop reordering
- Export/import of tasks
- Extra statuses (for example Blocked, Cancelled) or an Urgent priority

---

## 14. Documentation Requirement

The project must include a **README.md** at the repository root that covers:

- A short description of the product and what it does
- Setup and run instructions, from a fresh clone to a working application
- How to use it, with a list of supported chat commands and several example instructions
- Any configuration the user must provide before running (described at a high level)

---

## 15. Decisions Log

Decisions confirmed with the product owner, for traceability.

| # | Topic | Decision |
|---|---|---|
| 1 | Product framing | Assignment first, written so it can grow into a real product |
| 2 | Users | Single user, no login |
| 3 | Language | English only |
| 4 | Statuses | To do / In progress / Done |
| 5 | Priorities | Low / Medium / High; **default is Low** when none is given |
| 6 | Due dates | Date only, user's local time zone, resolved date always echoed back |
| 7 | "Move" | Same as changing status |
| 8 | Duplicate titles | Warn and ask before creating |
| 9 | Ambiguity | Numbered candidate list, no change until resolved |
| 10 | Delete safety | Always confirm; undo as a stretch goal |
| 11 | Multi-action | Multiple actions per message, plus filter-based bulk actions with preview and confirmation |
| 12 | Partial failure | Apply what is valid, report each outcome |
| 13 | Off-topic | Politely decline and list capabilities |
| 14 | Chat history | **Persists across refreshes**, with a Clear chat control |
| 15 | Search display | Chat list plus board filter with chip and "Show all" |
| 16 | Search relevance | Threshold applied; say so when nothing matches |
| 17 | Board layout | **Single list matching the reference rows** (circle, title, due label • status, priority badge), **organised in three status groups in the order To do → In progress → Done** |
| 18 | Manual controls | Complete checkbox and delete icon only |
| 19 | Mobile | Stacked, with the chat input pinned at the bottom |
| 20 | Sample data | Starts empty, with a "Load sample tasks" option |
| 21 | Response time | Under 5 seconds typical |
| 22 | AI unavailable | Show a clear error, change nothing |
| 23 | Submission material | Not part of the PRD; only the README requirement is included |
| 24 | Status order | To do first, then In progress, then Done (v1.1) |
| 25 | Filter persistence | Active filter is kept in the page address and survives a refresh (v1.1) |
| 26 | Due-date wording | Today, Tomorrow, weekday, Next week, then full date with year, for example "12 Nov 2026"; overdue tasks show "Overdue • N days" (v1.1) |
| 27 | Past due dates | Accepted when explicit, noted in the reply, shown as Overdue (v1.2) |
| 28 | Status changes | Any status to any other, including Done back to In progress or To do; completed time cleared on reversal (v1.2) |
| 29 | Date reading | Weekday = next upcoming; no year = next occurrence; ambiguous numeric dates asked; impossible dates rejected; more than one year ahead confirmed (v1.2) |
| 30 | Field limits | Title 200, description 1,000, message 1,000 characters (v1.2) |
| 31 | Unsupported or unclear requests | Not understood: ask with examples. Unsupported features and non-English: polite explanation (v1.2) |
| 32 | "Delete everything" | Bulk delete with total count and stronger confirmation (v1.2) |
