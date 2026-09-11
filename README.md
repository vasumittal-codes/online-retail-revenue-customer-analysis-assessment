# Online Retail II - Data Analyst Assessment

## Project question
Where is revenue concentrated, where is it leaking, and which customers need the most attention?

## Dataset
**Online Retail II**, UCI Machine Learning Repository.

- Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii
- Dataset download: https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip
- Raw size: 1,067,371 transaction rows, 8 fields
- Period: 01-Dec-2009 to 09-Dec-2011
- License: CC BY 4.0

The assessment requires an independently selected public dataset with at least 50,000 records or comparable complexity. This dataset comfortably clears that bar.

## What's included

`assessment_workbook.xlsx` contains Q1-Q10, plus `Data` and `Processed Data` tabs. The `Data` and `Processed Data` tabs include a small public-preview sample; the full source is intentionally not redistributed in this ZIP and is downloaded by the reproducible Python pipeline.

`src/build_assessment.py` is the main reproducible pipeline. It downloads the UCI file, combines the two Excel sheets, standardizes types, separates cancellations, removes duplicate and non-product rows, creates SalesValue, and produces analysis-ready CSV outputs.

`presentation/Online_Retail_Management_Presentation.pptx` is the 7-slide management presentation.

`dashboard/index.html` is a lightweight dashboard mock with simple filters; `dashboard/LOOKER_STUDIO_SETUP.md` explains how to rebuild it as a live Looker Studio dashboard from the processed CSVs.

`assets/` contains the supporting charts used in the deck and dashboard mock.

## Important reproducibility note

This runtime could not download the 43.5 MB UCI binary directly. To avoid inventing row-level results, the workbook uses verified benchmark figures from a public reproducible analysis of the same UCI dataset and labels the full raw-data step clearly. Before final submission to an evaluator, run the pipeline once with internet access:

```bash
python -m pip install -r src/requirements.txt
python src/build_assessment.py
```

Then upload the generated processed data / analysis outputs to Google Sheets and publish the dashboard through Looker Studio.

## Benchmark findings used in the management story

These figures come from a publicly documented, reproducible analysis of the same UCI Online Retail II dataset:

- Clean sales lines: 1,003,340
- Cancellation/return lines kept separately: 17,914
- Revenue: about GBP 19.64M
- Identified customers: 5,852
- UK revenue share: 85.5%
- November revenue: about GBP 1.43M in 2010 and GBP 1.45M in 2011
- Champions: 25.2% of customers, 69.2% of identified-customer revenue
- At Risk: 14.1% of customers, 9.3% of identified-customer revenue
- Month-1 repeat: about 21%
- Lifetime repeat: about 72%
- Cancellation/return revenue rate: about 3.65%

Reference analysis: https://github.com/ndkn-code/online-retail-analytics

