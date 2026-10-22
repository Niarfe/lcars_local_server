# Spatial Workspaces
## A Design Manifesto for Human-Centered Information Environments

**Status:** Foundational design principles — exploratory  
**Potential applications:** LCARS, standalone spatial workspace, personal knowledge management, document archives, media libraries, research environments

---

## Vision

Build a digital environment that organizes information in ways that human beings can recognize, remember, and manipulate naturally.

Instead of requiring people to remember filenames, directory structures, application boundaries, and sequences of navigation actions, provide stable, meaningful places for information.

A document might live in a filing cabinet. A book might occupy a familiar shelf. A project might have a desk covered with its current materials. A meeting folder might contain an agenda, a calendar, correspondence, photographs, and supporting documents, arranged so their relationships are immediately understandable.

These representations are not intended merely to imitate physical objects or make software attractive.

**Their purpose is to reduce cognitive effort by turning information into recognizable objects, arrangements, and places.**

The underlying files and applications remain authoritative. The spatial environment is a presentation and organization layer over those resources.

Its purpose is not to replace the filesystem, but to make the information within it easier to find, understand, compare, and remember.

---

## Principle 1 — Space carries meaning

Physical location is a form of information.

People often remember where something was encountered even when they cannot remember its exact name.

A book was on the upper shelf. A letter was inside the third drawer. A photograph was clipped to the corner of a document. A note was tucked beneath a calendar.

These are meaningful memories, not incidental details.

A digital workspace should be able to preserve similar associations.

Objects should occupy stable, recognizable locations. Spatial placement should reflect user intent, context, and relationships rather than being determined exclusively by filenames, sorting algorithms, or current search results.

**A document's location in the virtual environment should be independent of its location in the underlying storage system.**

The same source document may have meaningful placements in several rooms, shelves, or project folders without requiring duplicated files.

### Design implication

Spatial arrangements must be persistent. Automatic sorting and categorization can coexist with personally arranged locations, but must not silently disrupt them.

---

## Principle 2 — Preserve the physicality of books

Physical books provide an unusually effective model for navigating information.

A reader can remember that a passage occurred near the beginning, toward the bottom of a right-hand page, or shortly after a particular illustration.

A bookmark has a physical position. The thickness of pages before and after the bookmark communicates progress. The book's shape and organization reinforce orientation.

More importantly, a physical book supports nonsequential exploration.

A reader can keep a finger on page 35 while opening page 109 to compare a quotation. Both locations remain available. The earlier page has not been conceptually discarded merely because another page is being examined.

Many digital readers replace these relationships with a serialized stream.

A user navigates from one page to another, often losing the earlier context. Returning requires additional navigation and mental effort.

A spatial workspace should restore the ability to maintain several meaningful positions within the same resource.

### Design implication

Digital books and multipage documents should support:

- Visible bookmarks representing meaningful locations.
- Multiple simultaneously open pages or passages.
- Temporary page holding and comparison.
- Persistent reading positions.
- Recognizable visual progress through a document.
- Direct return to a preserved location without reconstructing navigation history.

A bookmark should feel like a retained place, not merely an invisible page number stored in application state.

**The reader should be able to explore elsewhere without losing where they were.**

---

## Principle 3 — Context should remain present, even when partially hidden

Physical workspaces allow information to remain present without remaining fully visible.

A paper partly covers another paper. A photograph is clipped to a folder. A calendar is tucked underneath an agenda. A bookmark protrudes from a closed book.

These arrangements convey the existence, identity, and location of information without requiring every detail to compete for attention.

This is **latent information**: material that is not currently in focus but remains recognizable and immediately accessible.

Conventional interfaces frequently treat visibility as binary. A resource is either open and displayed or hidden behind another window, tab, application, or navigation history.

Spatial workspaces should offer richer states:

- Foreground
- Adjacent
- Partially exposed
- Underneath
- Tucked away
- Bookmarked
- Immediately revealable

### Design implication

Objects should retain visible cues to their existence and relationships, even when their detailed contents are concealed.

**Information can be out of sight without being out of context.**

---

## Principle 4 — Reveal rather than compress

Modern digital interfaces frequently maximize information density.

Dashboards fill available space with panels, indicators, calendars, navigation controls, summaries, and status information.

This can be useful, but it can also make every element compete for attention.

One reason for this pressure is that conventional interfaces often make hidden information inconvenient to retrieve. Designers compensate by trying to display everything simultaneously.

A spatial interface offers another approach.

A central document can be generously sized and readable. Supporting material can sit nearby, partially exposed, or beneath it. Additional detail can be revealed with a small interaction rather than permanently squeezed into the visible page.

### Design implication

Prefer meaningful layering, adjacent context, and easy revelation over excessive compression.

Do not treat maximizing occupied screen area as an inherent measure of efficiency.

**The objective is not to display the most information. It is to make relevant information easiest to understand and retrieve.**

---

## Principle 5 — Empty space is functional

Margins, desk surfaces, folder edges, visible paper borders, and gaps between objects are not necessarily wasted space.

They help establish:

- Object identity.
- Grouping and separation.
- Visual hierarchy.
- Attention and focus.
- Spatial orientation.
- Awareness of partially hidden information.

A folder needs enough visible structure to be perceived as a folder. A document needs sufficient surrounding space to feel like an identifiable object rather than another interchangeable rectangle.

The user should be able to understand the arrangement before reading every label.

### Design implication

Preserve visual breathing room deliberately.

Allow a primary object to dominate attention while supporting information remains quiet but available.

**Space is part of the interface, not merely unused display capacity.**

---

## Principle 6 — Physical metaphors support recognition and memory

The interface should employ recognizable representations of familiar objects where those representations improve understanding.

Examples include:

- Books and bookshelves.
- Folders and filing cabinets.
- Papers and paperclips.
- Desks and worktables.
- Calendars and clocks.
- Photographs and contact sheets.
- Index cards and drawer labels.
- Maps, doors, rooms, and corridors.

These representations need not be photorealistic.

A static illustration or lightly textured object may be sufficient to evoke the familiar physical concept.

The important property is that users can recognize an object, understand its expected behavior, and form durable memories of interacting with it.

A distinctive folder containing recognizable papers may be more memorable than several identically styled application windows.

### Design implication

Visual identity is functional.

Objects should have recognizable forms, consistent behavior, and stable relationships.

The system may support different visual themes, from a modern office to an old scholarly library or a futuristic LCARS environment.

However, changing a visual theme must not invalidate the user's underlying spatial organization.

**The purpose of visual realism is recognition, not spectacle.**

---

## Principle 7 — Movement should explain what happened

Instantaneous transitions are not always the most cognitively useful transitions.

When one document disappears and another instantly replaces it, users may need to reconstruct mentally what changed and where the original material went.

A modest movement can preserve continuity.

Lifting a sheet reveals another beneath it. Sliding a photograph aside exposes a note. Pulling a folder forward distinguishes it from the folders around it.

These actions establish a sequence that can be remembered.

The interface need not simulate real-world physics. It only needs enough movement to communicate object identity, continuity, and changing relationships.

### Design implication

Use brief, purposeful transitions for actions such as:

- Lifting.
- Revealing.
- Sliding.
- Opening.
- Returning.
- Pinning.
- Comparing.
- Placing.

Movement should have a recognizable origin and destination.

Avoid elaborate animation that delays work without improving understanding.

Allow reduced-motion or immediate transitions for accessibility and expert use.

**A useful transition is an explanation, not a decoration.**

---

## Principle 8 — Preserve context during exploration

Exploring one resource should not destroy the arrangement that led to it.

A researcher examining a meeting agenda may need to inspect the attendee list, consult a calendar, compare a supporting memorandum, and return to the agenda.

These are parts of one activity, not unrelated application sessions.

The workspace should retain the relationships among them.

The user should be able to move a document aside, temporarily expand another, compare two items, and return them to their previous locations.

### Design implication

Support a small vocabulary of context-preserving actions:

**Reveal, lift, compare, hold, pin, associate, return, and restore.**

Workspace state should include object placement, stacking order, selected pages, bookmarks, and other meaningful context.

Closing and reopening a workspace should restore the arrangement whenever practical.

**Exploration should not require rebuilding the context from which exploration began.**

---

## Principle 9 — Organize around human activities, not application boundaries

A real-world project folder may contain an agenda, photographs, correspondence, notes, reference documents, and a calendar.

These objects belong together because they support one activity.

On a computer, however, they may live in entirely different applications and services.

A spatial workspace should assemble related resources by meaning and use rather than by file format or storage provider.

A meeting dossier might contain references to:

- A Markdown agenda in a Git repository.
- A PDF stored locally.
- A document linked from SharePoint.
- A live calendar event.
- An attendee directory.
- Notes maintained in another application.

These resources should appear together because the user considers them related.

The interface must respect the capabilities, authentication, and permissions of each underlying source. Not every resource can necessarily be edited or embedded directly.

### Design implication

A spatial folder contains references and presentation metadata, not necessarily copies of its contents.

**The folder represents an activity or relationship, not a physical storage directory.**

---

## Principle 10 — Stable places and multiple paths must coexist

Human memory benefits from stable locations, but efficient software also requires flexible retrieval.

A document may belong simultaneously to a research project, an academic institution, a particular semester, and a collection of ideas.

It should be possible to encounter the same underlying resource through several meaningful places.

Tags, metadata, search, and automatic classification can suggest associations. Users should also be able to establish deliberate placements.

Those placements should remain stable unless intentionally changed.

### Design implication

Support two complementary organizational systems:

**Semantic organization:** Tags, queries, search, source metadata, and automatically generated collections.

**Spatial organization:** Rooms, shelves, drawers, folders, stacks, and user-chosen arrangements.

These systems should reinforce each other without being confused.

A resource can have multiple visual references while retaining one authoritative underlying identity.

---

## Principle 11 — Spatial browsing and expert navigation are complementary

A memorable environment should not force users to perform lengthy physical simulations for routine work.

Walking through a hallway can be useful for orientation, exploration, and establishing a sense of place.

But a user who already knows a destination should be able to jump directly there.

The same workspace should support both:

**Exploratory interaction:** Browse shelves, inspect nearby materials, open drawers, examine objects, and follow visible relationships.

**Expert interaction:** Use keyboard shortcuts, search, direct navigation, and commands to reach familiar destinations rapidly.

These modes serve different cognitive purposes.

Neither should invalidate the other.

### Design implication

Every meaningful location should have a stable identity that can be reached through navigation or direct commands.

Keyboard-centric workflows, including vim-inspired commands, should coexist with spatial interactions.

**Physical metaphor should support efficient work, not impose unnecessary ceremony.**

---

## Principle 12 — The underlying systems remain the source of truth

The spatial interface is a presentation, navigation, and contextual organization layer.

It should not require moving documents into proprietary storage structures or duplicating files merely to arrange them visually.

A resource may reside on the local filesystem, in a repository, on a network share, or in a connected external service.

The spatial workspace stores the information required to find and present that resource:

- Stable resource identity.
- Source reference.
- Metadata and associations.
- Virtual placements.
- Presentation preferences.
- Relevant interaction state.

Where possible, content modifications should be performed through the authoritative underlying application or data source.

The interface must make unavailable or disconnected resources recognizable without silently losing their saved positions.

### Design implication

Maintain a clear separation between content and presentation.

The system should be inspectable, portable where practical, and compatible with existing tools.

**LCARS remains a layer over the underlying systems, not a replacement for them.**

---

## Principle 13 — Different environments can express different forms of work

A spatial system need not present every activity using the same metaphor.

A library is appropriate for books and research papers.

A filing cabinet is appropriate for records and archived documents.

A desk is appropriate for active work.

A gallery is appropriate for visual collections.

A theater is appropriate for media consumption.

An engineering room or LCARS console may be appropriate for operational dashboards and development tools.

Rooms provide recognizable context, while their contents provide useful interaction.

The world should be extensible without requiring every room to become a fully simulated three-dimensional environment.

### Design implication

Use a shared resource catalog and interaction model underneath multiple presentation styles.

Different rooms may be 2D, 2.5D, or 3D depending on the actual benefits of spatial depth.

The environment should remain useful on a conventional monitor without special glasses, while allowing stereoscopic presentation where beneficial.

---

## Principle 14 — Measure success by reduced cognitive effort

Visual sophistication is not the ultimate measure of success.

A spatial workspace should improve the user's ability to:

- Find previously encountered information.
- Recognize resources without remembering exact filenames.
- Maintain context while comparing documents.
- Resume interrupted work.
- Understand relationships between materials.
- Remember where useful information was encountered.
- Navigate between activities without becoming disoriented.

These outcomes should guide development priorities.

When evaluating a feature, ask:

**Does this representation make the information easier to recognize, remember, retrieve, compare, or use?**

If an animation, visual effect, room, or object does not provide a useful benefit, it may not justify its cost.

If a small static visual cue substantially improves recognition, it may be more valuable than a complex technical feature.

The environment should be designed around the cognitive experience of working with information.

---

# Architectural Commitments

The project should preserve a clear separation among three layers.

### A. Information and resource layer

The underlying source systems remain authoritative.

This layer resolves resources, tracks identifiers, retrieves metadata, and performs permitted content operations.

### B. Spatial and contextual layer

This layer maintains the user's virtual organization.

It stores rooms, shelves, drawers, folders, document references, associations, spatial arrangements, bookmarks, and workspace state.

This is the primary new capability.

### C. Presentation and interaction layer

This layer renders the environment and supports interaction.

It provides recognizable object representations, themes, lightweight animation, keyboard navigation, and optional stereoscopic rendering.

The same spatial organization should remain meaningful across different visual themes and presentation technologies.

---

# First Experimental Prototype

## The Dossier Desk

Before developing complete navigable buildings or elaborate 3D environments, validate the design through one small, recognizable workspace.

A folder lies open on a desk.

It contains several independent resources, such as an agenda, supporting memorandum, calendar, attendee photographs, and handwritten-style notes.

The objects have stable, partially overlapping positions.

The user can lift one document, reveal another, compare two items, bookmark a page, and return each object to its original location.

The workspace should preserve its arrangement between sessions.

The initial implementation may use static visual assets, layered HTML elements, CSS transforms, and short transitions. Full physical simulation is unnecessary.

The prototype should demonstrate the central cognitive promise:

**Related information can remain present, recognizable, and spatially organized without being simultaneously exposed or compressed onto one crowded screen.**

Success is demonstrated not by realistic page-turning effects, but by the user's ability to work with several resources without losing their relationships or locations.

---

# Guiding Statements

**Space is information.**

**Recognition can be more useful than recall.**

**Context should be near, not noisy.**

**Reveal rather than compress.**

**A bookmark preserves a place, not merely a number.**

**A document may exist in many meaningful places without being duplicated.**

**Movement should clarify relationships.**

**Exploration should preserve context.**

**Visual identity serves memory.**

**The filesystem stores information; the spatial environment helps the user remember and use it.**

---

## Closing Vision

The goal is not to recreate an old-fashioned office inside a computer.

Nor is it to turn practical work into a video game.

The goal is to restore useful qualities of physical interaction that conventional digital interfaces often discard: stable locations, recognizable objects, layered access, contextual relationships, simultaneous reference, and a sense of continuity.

A digital environment can provide capabilities far beyond physical paper while preserving the familiar structures that make paper effective.

A virtual book can open to two places at once. A folder can contain resources from different systems. A filing cabinet can reorganize its contents through metadata without moving the underlying files. A desk can preserve the exact arrangement of an unfinished activity.

A room can become a memorable entry point into an entire domain of work.

The technology should make these capabilities possible without forcing the user to think constantly about the technology itself.

**The ultimate ambition is an interface that remembers not only what information exists, but how the user relates to it.**

And when the user returns, the information should feel as though it is still where they left it.


