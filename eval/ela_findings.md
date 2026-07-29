# Does ELA detect the tampered IDs?

Error Level Analysis re-saves an image as JPEG and measures how far each
region moves. A region with a different compression history — pasted,
painted over, re-rendered — moves more than its surroundings. Scoring is
block-wise: `top_z` is how many robust deviations the most anomalous 16x16
block sits above the typical block.

## 1. Control — a genuinely edited JPEG

A clean ID saved as JPEG, reopened, an edited date pasted over it, re-saved.

| image | top_z | hot blocks | max error |
|---|---|---|---|
| unedited | 15.81 | 101 | 40.0 |
| edited | 12.7 | 61 | 28.0 |

**The edit does not stand out** (12.7 vs 15.81).

## 2. The dataset

30 IDs, 3 flagged `tampered_id` in the ground truth.

| patient | tampered | top_z | hot blocks | max error |
|---|---|---|---|---|
| PT_15075 | no | 48.43 | 537 | 105.0 |
| PT_16658 | no | 453.72 | 686 | 157.0 |
| PT_17665 | no | 66.26 | 505 | 105.0 |
| PT_19116 | no | 76.83 | 151 | 186.0 |
| PT_20322 | no | 58.66 | 459 | 86.0 |
| PT_20745 | no | 77.43 | 512 | 142.0 |
| PT_24208 | no | 21.7 | 244 | 77.0 |
| PT_24993 | no | 28.78 | 166 | 87.0 |
| PT_30028 | no | 53.67 | 498 | 78.0 |
| PT_39451 | no | 85.83 | 122 | 197.0 |
| PT_39816 | no | 40.69 | 178 | 107.0 |
| PT_41439 | no | 32.28 | 353 | 113.0 |
| PT_45400 | no | 21.7 | 244 | 77.0 |
| PT_47353 | no | 85.83 | 134 | 197.0 |
| PT_50538 | no | 85.83 | 119 | 197.0 |
| PT_54236 | no | 453.72 | 688 | 157.0 |
| PT_55056 | no | 453.72 | 688 | 157.0 |
| PT_57795 | **yes** | 42.84 | 301 | 91.0 |
| PT_62350 | no | 28.24 | 239 | 90.0 |
| PT_62383 | **yes** | 27.44 | 165 | 91.0 |
| PT_67125 | no | 85.83 | 120 | 197.0 |
| PT_69470 | no | 65.46 | 502 | 105.0 |
| PT_71993 | no | 453.72 | 684 | 157.0 |
| PT_72021 | no | 453.72 | 689 | 157.0 |
| PT_74454 | **yes** | 66.26 | 502 | 105.0 |
| PT_81810 | no | 66.26 | 504 | 105.0 |
| PT_82132 | no | 23.65 | 165 | 91.0 |
| PT_88139 | no | 82.51 | 147 | 197.0 |
| PT_99687 | no | 16.7 | 81 | 117.0 |
| PT_99733 | no | 453.72 | 687 | 157.0 |

Tampered: 27.44–66.26. Clean: 16.7–453.72.

**Separable: no.** The tampered range sits entirely inside the clean range.

## The bigger finding: the signal isn't in the images

While investigating why nothing separated, I read the generator. The three
clusters flagged `tampered_id` have no tampering rendered on them at all.

`generate_docs.py` defines a tamper branch inside `_id_drivers_license` and
`_id_passport` (draws the expiry date in a larger font and a different
colour), but the dispatcher never passes the argument:

```python
def generate_id_document(c, expired=False, blur=False):
    return _ID_GENERATORS[c['id_type']](c, expired=expired, blur=blur)
```

`tampered=` appears at no call site in the file, so that branch is dead code.
And the three flagged patients were assigned `state_id` (C_013, C_018) and
`insurance_card` (C_029) templates, whose generator functions don't accept a
`tampered` parameter in the first place.

Placing the tampered and clean versions of the same template side by side
confirms it: the cards are pixel-identical in styling, differing only in the
member's own data.

So these three cases are undetectable by *any* method — vision model, ELA, or
typographic analysis — because there is nothing in the image to detect. They
are ground-truth labels with no corresponding evidence, in the same category
as C_004's missing structuring amount.

This also explains the earlier prompt-tuning results. Wording that appeared
to 'catch tampering' was producing false positives on clean scans and getting
credit for it by coincidence; there was never a true positive to find. That
is the strongest possible argument for keeping the tamper flag advisory.

## Why ELA doesn't work here either

These documents are synthetic renders: sharp text on flat backgrounds. The
ELA map is dominated by glyph edges, which produce high error everywhere
text appears, so a localized edit has nothing to stand out against. The
control confirms this — even a deliberate paste onto a real JPEG fails to
rise above the text-edge noise floor.

There's a second reason specific to the source images: they are losslessly
generated PNGs, so every pixel shares the same empty compression history.
Some tampered and clean cards score *identically* because they are the same
template rendered with different field values.

ELA is built for natural photographs, where compression history varies and
there are no razor-sharp synthetic edges. On a photographed or scanned ID it
is a reasonable check. On this dataset it carries no signal.

## Consequence for the system

`ela_top_z` is attached to the KYC output and shown to the reviewer, but it
gates nothing — a signal measured to be uninformative should not move a
decision. Detecting this dataset's tampering needs field-level typographic
comparison instead: locate each labelled field, compare glyph height and
colour against its siblings, flag the outlier. That's a different technique
and is listed as future work.