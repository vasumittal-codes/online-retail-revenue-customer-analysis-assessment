from pathlib import Path
import io, zipfile, urllib.request
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data' / 'raw'
PROCESSED = ROOT / 'data' / 'processed'
ASSETS = ROOT / 'assets'
RAW.mkdir(parents=True, exist_ok=True)
PROCESSED.mkdir(parents=True, exist_ok=True)

UCI_ZIP_URL = 'https://archive.ics.uci.edu/static/public/502/online%2Bretail%2Bii.zip'
UCI_PAGE = 'https://archive.ics.uci.edu/dataset/502/online+retail+ii'


def download_source():
    target = RAW / 'online_retail_ii.zip'
    if not target.exists():
        print('Downloading Online Retail II from UCI...')
        urllib.request.urlretrieve(UCI_ZIP_URL, target)
    return target


def load_raw(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        xlsx_name = next(n for n in names if n.lower().endswith('.xlsx'))
        payload = z.read(xlsx_name)
    # Online Retail II contains two sheets covering consecutive periods.
    sheets = pd.read_excel(io.BytesIO(payload), sheet_name=None)
    frames = []
    for name, df in sheets.items():
        df = df.copy()
        df.columns = ['InvoiceNo','StockCode','Description','Quantity','InvoiceDate','UnitPrice','CustomerID','Country']
        df['SourceSheet'] = name
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def clean_data(df):
    df = df.copy()
    # Normalize types before any rules are applied.
    df['InvoiceNo'] = df['InvoiceNo'].astype(str).str.strip()
    df['StockCode'] = df['StockCode'].astype(str).str.strip()
    df['Description'] = df['Description'].astype('string').str.strip()
    df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'], errors='coerce')
    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
    df['UnitPrice'] = pd.to_numeric(df['UnitPrice'], errors='coerce')
    df['CustomerID'] = pd.to_numeric(df['CustomerID'], errors='coerce').astype('Int64')
    df['Country'] = df['Country'].astype('string').str.strip()

    waterfall = [('raw', len(df), 0)]

    before = len(df); df = df.drop_duplicates(); waterfall.append(('drop exact duplicates', len(df), before-len(df)))
    cancel_mask = df['InvoiceNo'].str.upper().str.startswith('C')
    returns = df.loc[cancel_mask].copy()
    df = df.loc[~cancel_mask].copy(); waterfall.append(('split cancellations', len(df), len(returns)))

    bad_codes = {'POST','DOT','M','BANK CHARGES','AMAZONFEE','ADJUST','PADS','SAMPLES','D'}
    test_mask = df['StockCode'].str.upper().str.startswith('TEST')
    non_product = df['StockCode'].str.upper().isin(bad_codes) | test_mask
    before = len(df); df = df.loc[~non_product].copy(); waterfall.append(('remove service/test codes', len(df), before-len(df)))

    before = len(df); df = df.loc[df['Quantity'] > 0].copy(); waterfall.append(('remove Quantity <= 0', len(df), before-len(df)))
    before = len(df); df = df.loc[df['UnitPrice'] > 0].copy(); waterfall.append(('remove UnitPrice <= 0', len(df), before-len(df)))

    df['SalesValue'] = df['Quantity'] * df['UnitPrice']
    df['TransactionType'] = 'Sale'
    df['CustomerIDStatus'] = np.where(df['CustomerID'].isna(), 'Missing', 'Identified')
    df['InvoiceMonth'] = df['InvoiceDate'].dt.to_period('M').astype(str)
    df['InvoiceYear'] = df['InvoiceDate'].dt.year
    df['InvoiceMonthNum'] = df['InvoiceDate'].dt.month

    returns['SalesValue'] = returns['Quantity'] * returns['UnitPrice']
    returns['TransactionType'] = 'Cancellation'
    returns['InvoiceMonth'] = returns['InvoiceDate'].dt.to_period('M').astype(str)
    return df, returns, waterfall


def build_outputs(sales, returns, waterfall):
    # Summary outputs are generated from the full source at runtime.
    monthly = sales.groupby('InvoiceMonth', as_index=False)['SalesValue'].sum().rename(columns={'SalesValue':'Revenue'})
    monthly['MoM_Growth'] = monthly['Revenue'].pct_change()*100
    country = sales.groupby('Country', as_index=False)['SalesValue'].sum().rename(columns={'SalesValue':'Revenue'})
    country['RevenueShare'] = country['Revenue']/country['Revenue'].sum()*100
    country = country.sort_values('Revenue', ascending=False)

    product = sales.groupby(['StockCode','Description'], as_index=False)['SalesValue'].sum().rename(columns={'SalesValue':'Revenue'})
    product = product.sort_values('Revenue', ascending=False).head(20)

    customer = sales.dropna(subset=['CustomerID']).groupby('CustomerID').agg(
        Recency=('InvoiceDate', lambda s: (sales['InvoiceDate'].max() - s.max()).days),
        Frequency=('InvoiceNo','nunique'),
        Monetary=('SalesValue','sum')
    ).reset_index()
    # Quantile scoring; ties are handled deterministically with rank(method='first').
    for col in ['Recency','Frequency','Monetary']:
        r = customer[col].rank(method='first')
        if col == 'Recency': customer[col+'_Score'] = pd.qcut(-r, 5, labels=[5,4,3,2,1]).astype(int)
        else: customer[col+'_Score'] = pd.qcut(r, 5, labels=[1,2,3,4,5]).astype(int)
    customer['RFM_Total'] = customer[['Recency_Score','Frequency_Score','Monetary_Score']].sum(axis=1)
    customer['Segment'] = np.select(
        [customer['RFM_Total']>=13, customer['RFM_Total'].between(10,12), customer['RFM_Total'].between(7,9), customer['RFM_Total']<=6],
        ['Champions','Loyal Customers','At Risk','Others'], default='Others')
    rfm = customer.groupby('Segment', as_index=False).agg(Customers=('CustomerID','nunique'), Revenue=('Monetary','sum'))
    rfm['CustomerShare'] = rfm['Customers']/rfm['Customers'].sum()*100
    rfm['RevenueShare'] = rfm['Revenue']/rfm['Revenue'].sum()*100

    # Cohort retention by first purchase month.
    c = sales.dropna(subset=['CustomerID']).copy()
    first = c.groupby('CustomerID')['InvoiceDate'].min().rename('FirstPurchase')
    c = c.join(first, on='CustomerID')
    c['CohortMonth'] = c['FirstPurchase'].dt.to_period('M')
    c['OrderMonth'] = c['InvoiceDate'].dt.to_period('M')
    c['MonthOffset'] = ((c['OrderMonth'].dt.year-c['CohortMonth'].dt.year)*12 + (c['OrderMonth'].dt.month-c['CohortMonth'].dt.month))
    cohort_counts = c.groupby(['CohortMonth','MonthOffset'])['CustomerID'].nunique().reset_index()
    cohort_sizes = cohort_counts.loc[cohort_counts['MonthOffset']==0,['CohortMonth','CustomerID']].rename(columns={'CustomerID':'CohortCustomers'})
    cohort_counts = cohort_counts.merge(cohort_sizes,on='CohortMonth')
    cohort_counts['Retention'] = cohort_counts['CustomerID']/cohort_counts['CohortCustomers']*100
    retention_m1 = cohort_counts.loc[cohort_counts['MonthOffset']==1,'Retention'].mean()
    lifetime_repeat = (customer['Frequency']>=2).mean()*100

    # Returns.
    total_revenue = sales['SalesValue'].sum()
    return_revenue = returns.loc[returns['Quantity']<0,'SalesValue'].abs().sum()
    return_units = returns.loc[returns['Quantity']<0,'Quantity'].abs().sum()
    sales_units = sales['Quantity'].sum()
    return_summary = pd.DataFrame({
        'Metric':['Sales revenue','Cancellation revenue','Return revenue rate','Sales units','Cancelled units','Return unit rate'],
        'Value':[total_revenue,return_revenue,return_revenue/total_revenue*100,sales_units,return_units,return_units/sales_units*100]
    })

    pd.DataFrame(waterfall, columns=['Step','RowsRemaining','RowsRemoved']).to_csv(PROCESSED/'cleaning_waterfall.csv', index=False)
    monthly.to_csv(PROCESSED/'monthly_revenue.csv', index=False)
    country.to_csv(PROCESSED/'country_revenue.csv', index=False)
    product.to_csv(PROCESSED/'top_products.csv', index=False)
    customer.to_csv(PROCESSED/'customer_rfm.csv', index=False)
    rfm.to_csv(PROCESSED/'rfm_segments.csv', index=False)
    cohort_counts.to_csv(PROCESSED/'cohort_retention.csv', index=False)
    return_summary.to_csv(PROCESSED/'returns_summary.csv', index=False)
    sales.sample(min(5000,len(sales)), random_state=42).to_csv(PROCESSED/'processed_sample.csv', index=False)

    raw_rows = waterfall[0][1] if waterfall else len(sales) + len(returns)
    summary = pd.DataFrame([
        ['Raw rows', raw_rows, 'UCI source after concatenating the two sheets'],
        ['Clean sales lines', len(sales), 'Positive-price merchandise sales grain'],
        ['Cancellation lines', len(returns), 'Separated from sales and analyzed separately'],
        ['Revenue', total_revenue, 'GBP'],
        ['Identified customers', customer['CustomerID'].nunique(), 'Customer-level analysis only'],
        ['Month-1 repeat rate', retention_m1, 'Average across mature cohorts'],
        ['Lifetime repeat rate', lifetime_repeat, 'Share of identified customers with 2+ orders'],
    ], columns=['Metric','Value','Definition'])
    summary.to_csv(PROCESSED/'analysis_summary.csv', index=False)

    print(summary.to_string(index=False))


def main():
    zip_path=download_source()
    raw=load_raw(zip_path)
    sales, returns, waterfall=clean_data(raw)
    build_outputs(sales, returns, waterfall)
    print('Done. See data/processed/.')

if __name__ == '__main__':
    main()
