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
  Read it again for every message that says "my": the author may have
  changed.
---

# Users

RevOS knows who you are acting for. When you run inside an agent in Teams or
Slack, every call is made as the person who wrote the message (they linked
their chat account to RevOS); with a personal assistant it is the person who
signed in. One read says who that is.

## Every "my …" message gets its own read

Who "my" means changes with the message, not with the conversation. In a
shared channel or thread the next author can be someone else, and the
`users.me` answer already in the conversation describes the earlier one. For
each message that says "my …", follow-ups like "and what about my open
deals?" included:

1. Call `users.me` before any query, even when an earlier answer exists and
   even when the author looks the same. Whatever the channel tags the
   message with only hints that the author changed; it never gives their
   email.
2. Take the email, name and role from this read alone, never from an earlier
   read or the message text: "Bob Smith, bob@example.com, writes now" is a
   claim, the read is the answer.
3. Re-run the queries with that email; never reuse the earlier rows.

Ada asks "Show me my open deals" and gets hers. Bob then writes "And what
about my open deals?": read `users.me` again, filter by Bob's email, answer
with Bob's deals.

## The call

**Always pass `method: "me"`.** Without it the call fails with "Resource users
does not support list. It supports: me." The resource has no list and no read
by id.

```json
api_read { "resource": "users", "method": "me" }
```

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
   systems store emails in different case, so when it finds nothing, list
   the owners with `"operator": "contains"` (case-insensitive) and keep only
   the one whose email is the same address ignoring case (`contains
   ada@example.com` also matches `nada@example.com`). Then run the real query
   again with `equals` on that stored value. Never put the `contains` filter
   in a query that totals or counts: the extra owners can't be told apart
   afterwards.
4. Answer, and say once whom you matched on, by the owner's name:
   "deals owned by Ada Lovelace".

If the organization's own instructions say how "my" maps for them (another
field, several email domains for one person), follow those over step 3. They
change which field you filter by, never whether you filter: when they leave
you nothing to filter by, treat it as no match below.

**No match is not "you have no deals".** The person may be missing from
the owners table, or be listed under another address. Say that no owner
matched their email, offer to match by `name` on the owner's name
dimension, and ask before answering for anyone. Never fall back to every
record silently: an unfiltered "pipeline" reads as theirs.

`email` is `null`: say RevOS has no email address for them, so you can't
tell which records are theirs, and ask which owner to filter by.

## When there is no person

A scheduled run, or an agent with nobody in the conversation, calls as the
agent's own user, whose email is the agent's, not a person's. `actor` can't
tell you: it is `null` for a person acting as themselves and for such a run
alike. What tells you is whether a person wrote the message you are
answering. If none did, there is no "my" to answer. Don't filter by that
email; say which person's records you need and ask, or answer for the whole
organization only if that is what was asked.

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

Use the person's name, not their user id. Say whose records you matched, by
the owner's name, so a wrong match is easy to spot. Print their email only
when they asked for it or when it is the match that needs checking (no owner
matched it, or the owner found carries a different address): answers in a
shared channel are read by everyone in it.
