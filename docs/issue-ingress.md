# Issue ingress

RSI issue creation has two front ends and one taxonomy.

## Human web filing

The organization chooser exposes Task, Bug, Feature, and Idea forms. Each form:

- assigns the native taxonomy-v6 Issue Type;
- collects type-specific evidence and an observable close or decision condition;
- directs the filer to GitHub's native Label, Priority, and Project controls; and
- records required filing gates without copying authoritative metadata into the body.

The human owns the semantic title. Do not add type, status, domain, Project, or
homing markers. GitHub's native metadata remains authoritative even when the form
body records that the filer made the decision.

Ordinary forms do not ask for Triage, parentage, relationships, Standalone,
Slice, Mission, or Crew. These values are machine-derived or belong to later
triage. Tracker 📡 and Project 🧭 are structural types, Notification 🔔 is
workflow-generated, and Slice 🍰 retired in taxonomy v6.

## Authority by stage

| Stage       | Human judgment                                                                                          | Machine derivation                                                | Project-specific state                       |
| ----------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------- |
| Filing      | semantic title, Issue Type via form, domain label, Priority decision, explicit Project choice, evidence | `Filed by = Human 👨`, `Triage = Untriaged 📥`                    | existing governed membership enters `Inbox`  |
| Triage      | legal home, deliberate Standalone decision, scheduling judgment                                         | linked Triage from the verified native parent                     | Slice where the selected Project requires it |
| Active work | priority changes and scope decisions                                                                    | Mission, Crew, derived parent Status, machine-owned homing suffix | Status lifecycle                             |

Priority remains human judgment. Taxonomy v6 normally requires it on open work.
The form permits an explicit "cannot honestly judge yet" acknowledgement so the
intake path can surface that unresolved judgment instead of inventing a value.

## `ghbd` convergence

GitHub Issue Forms cannot bind arbitrary organization issue-field values. Humans
can set pinned native fields in the composer; the YAML form itself sets only its
supported top-level metadata, including Issue Type.

After an ordinary human `issues.opened` event, the installed `ghbd` App provides
the organization-wide convergence path:

```text
set Filed by = Human 👨
set Triage = Untriaged 📥
if governed Project membership already exists, set Status = Inbox
```

It does not infer Priority, a domain label, Project membership, parentage,
Standalone, Slice, or a title suffix. Reconciliation must reuse `gh-bot` doctrine
and taxonomy values rather than carrying a second mapping.

## Agent and operator filing

Agents do not render or submit these forms. They use `ghb issue create` with its
required type, priority, provenance, domain label, Project decision, and native
relationship declaration. `ghb` remains operator-scoped; it is not the webhook
runtime. Both paths converge on the same doctrine in `RSI-Software/gh-bot`.
