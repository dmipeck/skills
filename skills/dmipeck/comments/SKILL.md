---
name: comments
description: >-
  Write comments that say why, not what. Use when writing code or
  documentation.
---
# Comments

Calm down. Too many comments. Code read itself. Reader no need narrator.

## Law

**Comment never say what code do.** Code already say. Redundant comment = noise.

```go
// Increment counter.  <- NO. Code say this already.
count++
```

Only write comment when code do something **unusual** that confuse reader.
  Then say **why**, not what.

```go
// No early return: need counter++ to run on both paths.
if retry {
  count++
}
```

## What-comment OK where?

Documentation only. **Public surface = doc territory.** Those get
  long what-comment:

- Public function / method (doc comment)
- Public class / struct / type
- Package / module doc
- Public constant

Those = API. Reader call from outside, cannot see body. Tell them what,
  contract, behavior, args, returns. Internal guts no.

Private function, private field, internal var, inline statement → no
  what-comment. Only why-comment if unusual.
