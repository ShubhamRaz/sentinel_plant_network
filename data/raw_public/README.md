# Raw public datasets

Download and extract the original Mendeley files here. Do not edit original files. Keep each dataset's README, data dictionary, DOI/version record and licence with the downloaded archive. Raw data are ignored by Git so that large files and licence-sensitive content are not accidentally committed.

- Tomato irrigation/weather: https://data.mendeley.com/datasets/c837v6p8ph/2 (Version 2, CC BY 4.0; Version 1 is also available).
- Leaf Wetness and Agrometeorological Dataset: https://data.mendeley.com/datasets/sd4b8vpvyb/1 (CC BY-NC 4.0; non-commercial terms apply).
- Libelium olive-grove multisensor dataset: https://data.mendeley.com/datasets/cnfh4stzzx/2 (CC BY 4.0).

These are external benchmark datasets, not measurements from the Sentinel hardware or the target field. Do not join the datasets row-wise: locations, crops, sensors and sampling intervals differ. Use each for its stated evaluation scope and document any transfer assumptions.

## Corrected validation and provenance

The validation commands write a full SHA-256 checksum and file size for every supplied CSV/TSV input. After all dataset runs, retain results/real_data_validation/DATASETS_MANIFEST.json together with the JSON reports and derived CSVs. These generated outputs are git-ignored by design; archive them with the research record rather than assuming they are present in a repository clone.

For the Italian leaf-wetness dataset, the adapter defaults to the Europe/Rome timezone and a local 18:00–06:00 nocturnal window. Offset-aware timestamps are converted to this timezone; naive timestamps are interpreted as local time in this timezone. Confirm this assumption using the dataset documentation before citing nocturnal LWD results. Calibrate the leaf-wetness threshold against the source data dictionary and reference measurements.
