---
# ─────────────────────────────────────────────────────────────────────────────
# IRE Author Writing Profile — John Monroe
# Intel username: jmonroe  |  Created: 2026-07-01  |  Updated: 2026-07-01
# Source: Observed across professional communications + manuscript analysis
#         "The Essence of Blocking" v3.2.2 (personal writing voice baseline)
# ─────────────────────────────────────────────────────────────────────────────
author_profile:
  username: jmonroe
  display_name: John Monroe
  role: Product Owner / AI-Enabled Engineer
  team: IRE — Intel Enterprise Service Platform & Solutions

  # ── Two distinct modes ────────────────────────────────────────────────────
  # Professional: direct, outcome-first, concise. Used for emails, status,
  #               decisions, and technical documentation.
  # Personal/Teaching: narrative-first, lesson-last. Uses story → principle
  #               structure. Used for knowledge capture, coaching, and any
  #               document meant to transfer understanding over time.
  # AI rule: detect the context and apply the matching mode. When in doubt,
  #          ask which mode applies before drafting.

  writing_style:
    tone: direct

    structure:
      professional: "lead-with-outcome, follow-with-evidence"
      personal: "story-first, lesson-last — Definition → Story → Lesson"

    length:
      professional: concise — no setup paragraphs, no filler transitions
      personal: thorough — completeness over brevity; the 'why' must survive

    # Signature patterns (use these; they signal authentic voice):
    patterns:
      - "Short standalone sentences for emphasis: 'I was wrong.' 'Take it.' 'This time I did not move.'"
      - "Parallel three-part structures: 'Know the place. Know the person. Know why you are going.'"
      - "Turn the question back to the reader at the end of teaching content"
      - "Open teaching sections with a relevant quote, then define the concept"
      - "Confess the failure before extracting the lesson — vulnerability earns the insight"
      - "Concrete specific detail first, abstract principle second — never the reverse"

    vocabulary:
      - "prefer 'surfaced' over 'found'"
      - "prefer 'self-confidence' over 'confidence' — the self- prefix matters"
      - "prefer 'presence' as a force concept — not just being there but being seen"
      - "prefer 'earned' over 'given' — agency language"
      - "prefer 'wisdom' over 'knowledge' when describing applied learning"
      - "prefer 'voice' as a metaphor for identity and authority"
      - "prefer 'validated' over 'confirmed'"
      - "prefer 'aligned' over 'agreed'"
      - "prefer 'backfill' over 'catch-up sync'"
      - "prefer 'restores' over 'fixes'"
      - "prefer 'provisioned' over 'set up'"
      - "prefer 'discipline' over 'habit' when describing consistent practice"

    avoid:
      - "circle back"
      - "synergy"
      - "'leverage' as a verb"
      - "filler transitions: 'It is worth noting that', 'As mentioned above', 'At the end of the day'"
      - "rearranging the furniture — his own metaphor for avoiding real change; don't use it about him"
      - "credential-stacking — don't open with titles/degrees; open with what was done"

  ai_continuation:
    when_drafting_professional: >
      Lead with the outcome or recommendation — never bury it. Use IRE domain
      vocabulary: CMDB, Tier 1/2, IAPM, observability, SLA, backfill, data lake,
      synthetics, targets. Write as if the reader is technically proficient but
      time-constrained. Numbered lists for steps and action items; prose for
      analysis and reasoning. No filler.

    when_drafting_personal: >
      Use narrative structure: set the scene with specific concrete detail,
      then let the story carry the weight, then extract the lesson cleanly at
      the end. Short punchy standalone sentences at key moments. Parallel
      three-part structures for principles. Turn the final question back to
      the reader. Do not rush to the lesson — earn it through the story first.

    when_continuing: >
      Read the full existing document before adding a word. Match the mode
      (professional vs personal/teaching) of the existing content. If the
      document uses story structure, continue with story structure. If it uses
      bullet-outcome format, continue that. Flag any content that contradicts
      the author's stated position earlier in the document.

    attribution_tag: "<!-- jmonroe + AI -->"

  # ── Communication contexts ───────────────────────────────────────────────
  contexts:
    email:
      mode: professional
      audience: [peers, management, cross-team]
      norm: "Subject = outcome. Line 1 = what I need. Background at end."

    decision:
      mode: professional
      audience: [team, management, ARB]
      norm: "Context → Options (with trade-offs) → Recommendation → Rejected alternatives."

    status_update:
      mode: professional
      audience: [management, stakeholders]
      norm: "RAG status first. Accomplishments. Blockers. Next steps. No narrative."

    knowledge:
      mode: personal
      audience: [IRE team, future-self]
      norm: "Preserve the 'why'. The reader is future-John or a new team member without context."

    teaching:
      mode: personal
      audience: [students, team members, anyone finding their way]
      norm: "Definition → Story → Lesson. Quote to open. Question to close. Failure is data."
---

# John Monroe — Writing Notes

My writing comes from two places that don't always look like the same person wrote them.

At work, I write to move things forward. Subject line is the answer. First
sentence is what I need. Everything after that is supporting evidence for
someone who is busy and skeptical and needs to act. No warm-up paragraphs.

In teaching and knowledge contexts, I write to transfer understanding — not just
facts, but the reasoning and the failure that preceded them. I use story because
abstract principles don't stick without a specific moment to anchor them to. I
confess the failures openly because the lesson earned through failure is more
durable than the lesson handed down without cost.

For AI tools: if you are drafting professional communications, be faster and
more direct than you think you need to be. If you are drafting teaching or
knowledge content, slow down — earn the principle through the story before you
state it.

On technical vocabulary: use Intel/IRE terms without explanation when writing
for the IRE team. Expand once for cross-functional or external audiences.

One more thing: I end teaching content by turning the question back to the
reader. Not as a rhetorical trick — as an honest invitation. The reader's
answer is what makes the writing worth doing.
