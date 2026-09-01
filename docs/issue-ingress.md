# Issue ingress

RSI issue creation has two front ends and one taxonomy.

## Human filing

The organization issue chooser exposes Task, Bug, Feature, and Idea forms. Each
form creates a leaf issue with:

- a native taxonomy-v6 `Type`;
- a title ending in the untriaged `[📥]` homing marker;
- required `Priority` and org-core `Domain` answers;
- an explicit relationship declaration and optional suggested parent; and
- a type-specific observable close or decision condition.

Opening the form under a human account is the evidence for `Filed by: Human 👨`.
The issue remains `Triage: Untriaged 📥` until a maintainer verifies its home.
Forms do not infer Project membership, native parents, dependencies, Slice, or
Mission. Those choices require live repository and board context.

Tracker 📡 and Project 🧭 are structural types, so they are not human chooser
entries. Notification 🔔 is workflow-generated. Slice 🍰 retired in taxonomy v6.

## `ghb` convergence

The submitted Markdown headings are the browser-ingress contract:

- `Priority` is one of `Urgent`, `High`, `Medium`, or `Low`;
- `Domain` is one exact org-core label;
- `Relationship` and `Relationship target` map to one governed relationship
  flag; and
- `Suggested parent` is untrusted input until its native edge is verified.

Until `ghb` has a browser-ingress adapter, reconcile a new human filing with:

```text
ghb issue view OWNER/REPO#NUMBER
ghb issue edit OWNER/REPO#NUMBER
```

The interactive edit writes Priority, Triage, Filed by, the domain label,
Project membership, native structure, and the final homing suffix through the
same doctrine layer used by agents. A sweep can detect drift, but judgment fields
still require review.

## Agent filing

Agents do not render or submit these forms. They use `ghb issue create` with its
required `--type`, `--priority`, `--filed-by`, `--source`, domain `--label`,
Project decision, and relationship declaration. `ghb` composes the title suffix
and performs atomic preflight and readback. This keeps browser form parsing out
of the governed agent path.
