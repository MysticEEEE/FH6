# 2560×1440-native template re-cut report

Re-cut of every template in `images/` (root + `giftbox/`, `wheelspin/`, `obstacles/`)
into a clean 2560-native set under `images/1440P/`. **Image prep only — no `.py` changed.**

## Summary

| Result | Count |
|--------|------:|
| Templates processed | 65 |
| **OK** (re-cut + independently verified ≥0.90) | **33** |
| **MISSING** (not confidently locatable in the 2560 pool) | **32** |

All 33 saved crops were re-loaded and matched back against their original template
(opaque → multi-scale `CCOEFF_NORMED`; transparent → masked Pearson over opaque pixels):
**33/33 PASS, 0 fail.**

## Method

- **Source pool:** screenshots with width 2520–2600 (true 2560-native), 82 images, from
  `E:/FH6/screenshots/`, `E:/FH6/screenshots/2560/`, `E:/FH6/FH6/debug/snaps/`,
  `E:/FH6/FH6/debug/gift_seq/`. (4K/3840 and 2650-wide shots excluded — they would not be native.)
  Read via `cv2.imdecode(np.fromfile(...))` for Chinese paths.
- **Locate:** coarse search (0.30–0.40× downscale, scale grid 0.45–1.75) to shortlist the
  top-3 candidate screenshots, then **full-resolution** scale sweep on each (exact location,
  no coarse-offset error) + a ±0.06 fine scale refine.
- **Transparency-aware:** templates with >5% transparent pixels (RGBA alpha) are located with
  **masked** matching (`TM_CCORR_NORMED` + mask) and verified with masked Pearson correlation,
  because `IMREAD_COLOR` turns transparent pixels black and wrecks ordinary matching.
- **Accept gate:** match ≥0.85 AND independent re-verify ≥0.90, crop not empty/all-black.
- The locate-then-crop preserves the original framing/bounding box exactly; the crop is taken
  from the native 2560 screenshot, so output is true 2560-native.

### Three base-resolution families were found in the originals
The originals are a mixed bag; the located scale reveals each one's source base:
- **scale ≈1.0** — already 2560-native (most `giftbox/*`, `wheelspin/*`, `BNandUC`, `eventlab`, `collectionjournal`, `playenent`, `repitem`, `removecarobject`, `liketag`, `stat_*`…)
- **scale ≈1.6** — upstream ~1600-base, upscaled to native (`newCC`, `newcartag`, `skillcar`, `sharecode-dialog`, `VEI`, `classB600`)
- **scale ≈0.6–0.68** — 4K/3840-base, downscaled to native (`CCbrand`, `skillcarbrand`, `exit`, `startw`)

## OK — re-cut to `images/1440P/` (33)

| Template | Output size | Located scale | Verify |
|----------|-------------|--------------:|-------:|
| BNandUC.png | 305×112 | 1.00 | 1.000 |
| CCbrand.png | 90×34 | 0.60 | 0.958 |
| VEI.png | 191×57 | 1.62 | 0.954 |
| classB600.png | 113×41 | 1.59 | 0.984 |
| collectionjournal.png | 353×284 | 1.00 | 0.989 |
| eventlab.png | 283×146 | 1.00 | 0.945 |
| exit.png | 122×34 | 0.68 | 0.949 |
| liketag.png | 31×28 | 1.00 | 0.981 |
| newCC.png | 421×270 | 1.60 | 0.991 |
| newcartag.png | 74×42 | 1.60 | 0.976 |
| playenent.png | 342×328 | 1.00 | 0.954 |
| removecarobject.png | 417×309 | 1.00 | 0.979 |
| repitem.png | 140×54 | 1.00 | 0.991 |
| sharecode-dialog.png | 256×78 | 1.60 | 0.985 |
| skillcar.png | 419×278 | 1.60 | 0.945 |
| skillcarbrand.png | 90×34 | 0.60 | 0.958 |
| startw.png | 336×37 | 0.69 | 0.933 |
| giftbox/cannot.png | 890×96 | 1.00 | 1.000 |
| giftbox/confirm.png | 890×96 | 1.00 | 1.000 |
| giftbox/giftbox_entry.png | 170×68 | 1.00 | 1.000 |
| giftbox/msg.png | 892×96 | 1.00 | 1.000 |
| giftbox/recipient.png | 890×96 | 1.00 | 1.000 |
| giftbox/sent.png | 891×96 | 1.00 | 1.000 |
| giftbox/sign.png | 892×96 | 1.00 | 1.000 |
| giftbox/stat_chez.png | 222×58 | 1.00 | 0.971 |
| giftbox/stat_mali.png | 220×57 | 0.99 | 0.976 |
| giftbox/stat_paiqi.png | 136×57 | 0.99 | 0.986 |
| wheelspin/entry_super.png | 245×290 | 1.00 | 1.000 |
| wheelspin/entry_wheelspin.png | 210×290 | 1.00 | 1.000 |
| wheelspin/menu_anchor.png | 244×54 | 1.00 | 1.000 |
| wheelspin/owned.png | 310×67 | 1.00 | 1.000 |
| wheelspin/respin.png | 382×44 | 1.00 | 1.000 |
| wheelspin/skip.png | 188×59 | 0.99 | 0.933 |

No clipped/odd framing was observed among the OK set; all crop cleanly and verify high.

## MISSING — NOT confidently located in the 2560 pool (32)

These were **not** re-cut (best match below the 0.85 locate gate, or located but pixel-verify < 0.90).
`score` = best match found in the pool. **The user needs to capture clean 2560×1440 screenshots
of the screens below so these can be re-cut.**

| Template | best score | Note |
|----------|-----------:|------|
| EXPwU.png | 0.819 | near-threshold; mastery/EXP-up screen present but text didn't verify |
| consumablecar.png | 0.800 | near-threshold; "consumable car" tag not on the cards in pool |
| clsldcnb.png | 0.796 | near-threshold |
| choosecar-b.png | 0.788 | near-threshold (selected/black variant) |
| horizon6.png | 0.770 (located 0.972 / verify 0.742) | logo located on EXP-up shot but pixels differ; needs clean shot |
| continue-w.png | 0.746 | |
| continue-b.png | 0.725 | |
| likeauthor.png | 0.718 | creative-center author like |
| choosecar.png | 0.717 | |
| clsldcnw.png | 0.702 | |
| spraycar-w.png | 0.688 | design & paint context |
| UandT-b.png | 0.684 | upgrade & tune button |
| dislikeauthor.png | 0.674 | creative-center author dislike |
| designpaint-b.png | 0.671 | |
| designpaint-w.png | 0.649 | |
| UandT-w.png | 0.642 | |
| exit-b.png | 0.632 | |
| obstacles/exit-b.png | 0.632 | |
| restart.png | 0.619 | |
| buyandsell-b.png | 0.616 | |
| restarta.png | 0.605 | 44% transparent; opaque content not in pool |
| obstacles/restarta.png | 0.605 | 44% transparent; same as above |
| SPNE.png | 0.598 | notification/settings string |
| start.png | 0.585 | race start button |
| rc.png | 0.580 | |
| removecar.png | 0.566 | |
| racenotfound.png | 0.565 | error dialog |
| buyandsell-w.png | 0.564 | |
| VRAMNE.png | 0.536 | notification/settings string |
| masterexplorer.png | 0.525 | accolade popup |
| DSI.png | 0.478 | |
| carcollection.png | 0.460 | 81% transparent; icon not in pool |

### Screens to capture (grouped) so the MISSING set can be completed
1. **Car-options / "my car" action menu** (one screen likely yields several):
   `UandT-b/w`, `buyandsell-b/w`, `choosecar`/`choosecar-b`, `designpaint-b/w`, `spraycar-w`,
   `clsldcnb/w`, `removecar`, `DSI`, `rc`, `carcollection`, `consumablecar`.
2. **Race flow — start / pause / results / obstacle pause menu:**
   `start`, `restart`, `restarta`, `continue-b/w`, `obstacles/restarta`, `obstacles/exit-b`, `exit-b`.
3. **Creative-center author panel:** `likeauthor`, `dislikeauthor`.
4. **Status / error / notification dialogs:** `racenotfound`, `masterexplorer`, `VRAMNE`, `SPNE`,
   `EXPwU`, `horizon6` (loading/title with the Horizon 6 logo).

Note: `-b` / `-w` are black/white (normal vs highlighted/selected) variants of the same control;
a screen usually shows only one state at a time, so both variants of a control may need two shots.
