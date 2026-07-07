# Architecture Decision Records (ADRs)

This directory contains Architecture Decision Records (ADRs) for the Aloft backend. ADRs document important architectural decisions, their context, and consequences.

## What is an ADR?

An Architecture Decision Record is a document that describes an architectural decision, records the context, and explains the consequences. ADRs help teams:

- Understand why architectural decisions were made
- Communicate decisions to new team members
- Revisit and challenge decisions when context changes
- Maintain architectural history

## ADR Format

Each ADR follows this structure:

- **Status**: Accepted, Proposed, Deprecated, or Superseded
- **Context**: What is the issue that we're seeing that is motivating this decision?
- **Decision**: What is the change that we're proposing and/or doing?
- **Rationale**: Why is this solution better than alternatives?
- **Alternatives Considered**: What other approaches did we consider?
- **Consequences**: What becomes easier or more difficult because of this change?
- **Implementation**: How is this decision implemented?
- **References**: Links to relevant documentation

## Existing ADRs

- [ADR 0001: Use FastAPI for Backend Framework](0001-use-fastapi.md)
- [ADR 0002: Use MongoDB for Primary Database](0002-use-mongodb.md)
- [ADR 0003: Use Redis for Caching and Session Management](0003-use-redis-for-caching.md)
- [ADR 0004: Use ElevenLabs for Text-to-Speech](0004-use-elevenlabs-for-tts.md)
- [ADR 0005: Use Structured Logging with Correlation IDs](0005-use-structured-logging.md)

## Creating New ADRs

When making a significant architectural decision:

1. Create a new ADR file: `NNNN-title.md` (NNNN = sequential number)
2. Use the template from existing ADRs
3. Fill in all sections
4. Update this README with the new ADR
5. Commit the ADR with the implementation

## Modifying ADRs

When context changes and an existing decision needs to be revisited:

1. Add a new section "Superseded By" linking to the new ADR
2. Change status to "Superseded"
3. Create a new ADR documenting the new decision
4. Keep the old ADR for historical context

## ADR Template

```markdown
# ADR NNNN: Title

## Status
[Proposed | Accepted | Deprecated | Superseded]

## Context
[What is the issue that we're seeing that is motivating this decision?]

## Decision
[What is the change that we're proposing and/or doing?]

## Rationale
[Why is this solution better than alternatives?]

## Alternatives Considered
[What other approaches did we consider?]

## Consequences
- [Positive consequences]
- [Negative consequences]

## Implementation
[How is this decision implemented?]

## References
[Links to relevant documentation]
```

## References

- [Michael Nygard's ADR Template](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR Tools](https://adr.github.io/)
