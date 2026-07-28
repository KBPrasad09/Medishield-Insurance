# Demo video — script and shot list

Target length: 7 minutes. Anything past 10 loses people.

## Before you hit record

- [ ] Backend running, frontend running, both windows sized so you can switch fast
- [ ] Browser zoomed to 110–125%. Close every other tab. Hide bookmarks bar.
- [ ] Delete the leftover test cases. The dashboard should show only what you're demoing.
- [ ] Pre-load **C_007** (rejected) and **C_017** (approved) so they're already decided
- [ ] Have the five **C_001** files ready in an Explorer window — that's your live upload
- [ ] Open `eval/results.md` in a tab, scrolled to the summary table
- [ ] Do one dry run. The API takes 15–20 seconds on a 5-document case and you need to
      know what you're saying while it works.
- [ ] Turn off notifications

Record in one take if you can. Small stumbles are fine — they read as human. Long
silences while something loads don't.

---

## 0:00 — What this is (35 seconds)

**On screen:** the dashboard, a few decided cases visible.

> MediShield gets about 85,000 documents a month. Claim forms, ID scans, discharge
> summaries, prescriptions. Right now a person opens each one, checks the identity,
> types in the billing codes, looks up whether the policy covers the procedure, and
> tries to spot anything that looks off.
>
> This is a system that does that, and escalates the cases it shouldn't decide alone.
> Six agents, a decision graph, and a review queue for humans.

Don't read the architecture off a slide here. Show the working thing first.

---

## 0:35 — How it fits together (60 seconds)

**On screen:** the architecture diagram from the README, or draw it as you talk.

> A page comes in and gets classified — claim form, ID, discharge summary, and so on.
> Based on that, it goes to whichever specialist handles it. IDs go to KYC, which
> checks the person against the member roster. Claim forms go to extraction, which
> pulls the amount and the ICD and CPT codes and validates them. Then the policy agent
> takes those codes, retrieves the relevant clauses from the plan document, and decides
> coverage from the retrieved text.
>
> Those run per document, as soon as you upload. Fraud is different — it needs the
> whole case at once, because the patterns are things like the same claim submitted
> twice, or a prescription dated weeks after discharge. So fraud and the final decision
> run as a LangGraph state machine when the case is complete.

**Say this bit, it matters:**

> Every agent returns a typed schema, not free text. The call is a forced tool-use call
> where the tool's input schema *is* the agent's output contract. The model can't reply
> with prose and can't invent a document type. It also means text inside a scanned
> document can't change the shape of what comes back — which is the obvious injection
> route when you're feeding untrusted images to a model.

---

## 1:35 — Live upload (110 seconds)

**On screen:** dashboard → pick the five C_001 files → Case ID `C_001` → Upload.

> These five files are one patient episode. Same case ID.

It'll sit on the processing banner. Keep talking:

> Each page is being classified right now, and each one gets routed to its specialist.
> That's five classifier calls plus the extraction work, running in the background so
> the upload isn't blocking.

**When the tabs fill in**, click through two or three:

> Classifier got all five right. Here's the ID — KYC pulled the name and date of birth
> and matched it against the roster. Here's the claim form — amount, diagnosis codes,
> procedure codes, provider NPI, all extracted and schema-validated.

**Click Run decision.**

> Now fraud runs across the whole case, and the orchestrator makes the call.

---

## 3:25 — The escalation (55 seconds)

**On screen:** the decision card on C_001.

> ESCALATE. Fraud score 0.80, and it tells you why — the prescription date conflicts
> with the service date.

**Expand "Analyst notes":**

> The model wrote up what it noticed, but those notes are weighted zero. Only the two
> temporal patterns it was actually asked about can move the score. That's deliberate —
> early on it was flagging coverage problems as fraud, which double-counted the same
> fact and turned rejections into escalations.

**Expand the evidence trail:**

> And every agent's contribution is on the record. This is why the decision was made.

---

## 4:20 — Human in the loop (50 seconds)

**On screen:** Review Queue → C_001 → override.

> Escalate means a person decides. The case status flips to NEEDS_REVIEW and it lands
> here, with the fraud signals and the documents attached, so the reviewer isn't
> starting from scratch.

**Type a reason, click REJECT.**

> They make the call and it's recorded — who, when, why, and what the system had
> originally decided. The automated decision isn't overwritten. Both are in the audit
> trail.

---

## 5:10 — The other two outcomes (40 seconds)

**On screen:** C_007.

> Same pipeline, different answer. This one's rejected, and the reason is specific —
> CPT 17000 falls in the excluded range for cosmetic procedures, section 4.1. That
> clause came out of the policy PDF through retrieval. The model was told to decide
> using only the retrieved text, so the citation is real and you can go check it.

**Then C_017:**

> And a clean case just gets approved. Identity checks out, claim's valid, procedure's
> covered, no fraud signals. No human touches it.

---

## 5:50 — Numbers (50 seconds)

**On screen:** `eval/results.md`.

> This runs all 30 patient clusters and the four out-of-domain documents through the
> real pipeline and scores them against the dataset's ground truth.
>
> Classification 96%. Extraction 97%, with full CPT recall. Policy coverage 100%.
> Decisions, 26 of 34.

**Then be straight about the misses:**

> Eight wrong, and they come down to two signals. Tampered IDs — the dataset marks
> those by drawing the expiry date in a slightly different font, and prompts that catch
> it reliably also flag clean scans. I tried both ends of that and there's no wording
> that fixes both. It's a pixel problem, not a language problem, so I stopped treating
> the model's tamper flag as a decision gate and made it advisory. Error-level analysis
> is the right tool and it's the first thing I'd add.
>
> The other is a name-swap fraud where one vowel changes — Mary to Mery. Vision models
> silently correct the spelling as they read, so it comes back looking valid.

---

## 6:40 — Close (30 seconds)

> Both of those fail toward review rather than toward a wrong automatic decision, which
> is the direction you want. A reviewer spending five minutes on a clean case is
> cheaper than approving a fraudulent one.
>
> Repo's linked. The eval is reproducible — one command, and it writes that table.

Stop recording.

---

## Things that will bite you

**Don't click Run decision while the banner's still up.** Finalize only reads what's
already processed. You'll get a partial result on camera.

**Don't upload the same files twice.** Two claim forms in one case trips the duplicate
claim rule, and you'll be explaining a fraud signal you created yourself.

**If an API call fails mid-demo**, say so and move on to the pre-loaded cases. Recovering
calmly looks better than a re-record where nothing goes wrong.

**Update [YOUR NUMBER]** before you record. Run the eval once on the current code so the
figure you say out loud matches the file you're showing.
