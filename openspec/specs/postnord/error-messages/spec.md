# postnord/error-messages Specification

## Purpose
Defines how PostNord fault responses become unified messages, so that a message names what to correct in the unified request where the fault's subtype allows it, and keeps PostNord's own text and references.

## Requirements

### Requirement: Known fault subtypes carry a hint

When a PostNord fault's subtype reference names a condition that maps to a unified request field, the message SHALL start with PostNord's explanation text followed by a hint naming the unified field or setting to correct.
The fault's code and its references SHALL be kept unchanged, and a fault with an unknown subtype SHALL keep PostNord's explanation text as its message without a hint.

#### Scenario: Missing content fault names the commodity fields

- **WHEN** PostNord returns a fault with explanation text "content is a required field" and the reference `CustomerOriginValidationError.subType` = `CONTENT`
- **THEN** the message starts with "content is a required field" and names the customs commodity title or description, the code is `CONTENT`, and `details.references` still holds both references

#### Scenario: Unknown subtype keeps the text as is

- **WHEN** PostNord returns a fault whose subtype has no hint
- **THEN** the message equals PostNord's explanation text

### Requirement: Response summary is kept with the faults

When a PostNord error response carries a top-level message as well as faults with their own explanation text, each resulting message SHALL keep that top-level message in its details.

#### Scenario: Envelope message is kept

- **WHEN** PostNord returns `"message": "Invalid indata object EdiInstruction"` with a fault whose explanation text is "content is a required field"
- **THEN** the resulting message's details contain "Invalid indata object EdiInstruction"
