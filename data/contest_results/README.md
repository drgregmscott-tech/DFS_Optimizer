# Full contest results (lineup-level) -- one file per slate/contest

Raw DraftKings post-contest exports, unmodified (Rank, EntryId, EntryName, Points, Lineup string,
plus the Player / Roster Position / %Drafted / FPTS block in the right-hand columns).
Named `<site>_<slate_id>[_<contest>]_full.csv` -- name by slate_id, NOT by DK's download name
(DK labeled the wk3 ATL@GB export "wk2"). `_se3max` / `_mme` = contest type where more than one exists.

This is the lineup-level data `analysis/showdown_own/four_slate.py` needs (team split, kicker, DST,
CPT position, CPT-ownership tier vs top-10% rate). The player-level `data/results_raw_*` and
`data/ownership_raw_*` files remain the trimmed inputs to the logging scripts.

| file | slate |
|---|---|
| dk_showdown_wk1_Den_KC_14Sep2026_full.csv | Showdown DEN@KC |
| dk_showdown_wk2_Ind_KC_20Sep2026_full.csv | Showdown IND@KC |
| dk_showdown_wk2_NYG_LAR_21Sep2026_full.csv | Showdown NYG@LAR |
| dk_showdown_wk3_Atl_GB_24Sep2026_full.csv | Showdown ATL@GB (8,871 entries) |
| dk_classic_wk1_{early,afternoon,main}_13Sep2026_full.csv | Classic wk1 |
| dk_classic_wk2_{early,afternoon,main}_20Sep2026_se3max_full.csv | Classic wk2 3-max |
| dk_classic_wk2_main_20Sep2026_mme_full.csv | Classic wk2 main MME (22 MB) |
