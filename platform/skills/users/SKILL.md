---
name: users
description: >
  Find out who you are talking to in RevOS — the person's user id, email,
  name and role in the organization — through the RevOS MCP server, and use
  it to answer questions about "my" things: "my deals", "my pipeline", "my
  accounts", "deals I own", "tasks assigned to me", "what's on my plate". Use
  this before answering any question whose answer depends on who is asking,
  when the user asks "who am I" or "what's my role", and before filtering
  any query by an owner, assignee or sales rep meaning the asker. It only
  ever describes the asker: looking up a colleague is not possible here.
---

# Users

RevOS knows who you are acting for. When you run inside an agent in Teams or
Slack, every call is made as the person who wrote the message (they linked
their chat account to RevOS); with a personal assistant it is the person who
signed in. One read says who that is.

## The call

```json
api_read { "resource": "users", "method": "me" }
```

Always with `method: "me"`; the resource has no list and no read by id.

```json
{
  "id": "user_2x…",
  "email": "ada@example.com",
  "name": "Ada Lovelace",
  "organization": { "id": "…", "role": "member" },
  "actor": { "kind": "machine", "id": "mch_…" }
}
```

- **`email`** — their primary address, or `null` when they have none.
- **`name`** — first and last name, or `null`.
- **`organization.role`** — `viewer`, `member`, `developer` or `admin`. It is
  what they may do in RevOS, not their job title.
- **`actor`** — the agent acting for them, or `null` when they act as
  themselves. Either way `id`, `email` and `name` are the person's, never the
  agent's.

Call it once per conversation and reuse the answer. The person does not
change between turns, so don't call it again for every question.

## Answering "my …"

"My deals" means the records whose owner, assignee or rep is the asker. The
semantic model holds who owns what, the RevOS user does not. So:

1. Read `users.me` for `email` (and `name`).
2. In the semantic model (the `semantic-model` skill), find where the owner
   is: an owner dimension on the cube itself (`deals.owner_email`), or a
   join to an owners or users cube (`hubspot_owners.email`). Read the
   cube's `meta` rather than guessing a member name.
3. Filter by the email: `{ "member": "<owners cube>.email", "operator":
   "equals", "values": ["<email>"] }`. `equals` is case-sensitive and
   systems store emails in different case, so when it finds nothing, ask
   once more with `"operator": "contains"` (case-insensitive) and keep only
   owners whose email is the same address ignoring case.
4. Answer, and say once whom you matched on: "deals owned by
   ada@example.com".

If the organization's own instructions say how "my" maps for them (another
field, several email domains for one person), follow those over step 3.

**No match is not "you have no deals".** The person may be missing from
the owners table, or be listed under another address. Say that no owner
matched their email, offer to match by `name` on the owner's name
dimension, and ask before answering for anyone. Never fall back to every
record silently: an unfiltered "pipeline" reads as theirs.

`email` is `null`: say RevOS has no email address for them, so you can't
tell which records are theirs, and ask which owner to filter by.

## When there is no person

A scheduled run, or an agent with nobody in the conversation, calls as the
agent's own user: `actor` is `null` and the email is the agent's, not a
person's (often a `bot`/`agent`/`noreply`-style address). There is no "my"
to answer then. Don't filter by that email; say which person's records you
need and ask, or answer for the whole organization only if that is what was
asked.

## Errors

- **401 with `errors[0].code: "account_not_linked"`** — the person hasn't
  linked their chat account to RevOS yet. Every other call fails the same
  way. Say so; the agent's sign-in flow handles the link. Don't relay the
  link into a shared thread: it is single-use and personal.
- **403** — the credential acts for nobody (a machine credential with no
  person). Same as [When there is no person](#when-there-is-no-person).

## Not possible here

Looking up anyone else: "who owns this deal", "what's Bob's email", "list
the users". There is no such read in RevOS, by design. Answer from the
semantic model (owner names and emails in the CRM's owners cube) instead,
or say it isn't available.

## Reporting back

Use the person's name, not their user id. Don't print their email unless
it's what they asked for or what you matched on. Say what you matched on
when it shaped the answer, so a wrong match is easy to spot.
