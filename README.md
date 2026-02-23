# Biotech 13F Tracker

A Python tool to track and analyze 13F filings from 38 specialist biotech hedge funds and investment firms.

## Features

- **Track Latest Filings**: Get the most recent 13F-HR filings for all 38 biotech funds
- **Detailed Holdings**: Extract and analyze detailed holdings for any specific fund
- **Get All Holdings**: Fetch and save holdings for ALL funds at once
- **AUM Analysis**: Calculate Assets Under Management for each fund based on holdings value
- **Overlap Analysis**: Find stocks held by multiple funds (high conviction ideas)
- **Top Value Analysis**: Identify stocks with the highest total value held across all funds
- **Automated Data Collection**: Fetches data directly from SEC EDGAR API
- **CSV Export**: All data saved to CSV files for further analysis

## Funds Tracked (40 Total)

The tracker monitors these specialist biotech funds:

- Boxer Capital Management, LLC
- Checkpoint Capital
- Caligan Partners LP
- Octagon Capital Advisors LP
- Perceptive Advisors LLC
- Exome Asset Management LLC
- Avoro Capital Advisors LLC
- Affinity Asset Advisors, LLC
- ADAR1 Capital Management, LLC
- Saturn V Capital Management LP
- Greatpoint Partners
- Vestal Point Capital, LP
- RTW Investments, LP
- Soleus Capital Management, L.P.
- Ally Bridge Group (NY) LLC
- Ikarian Capital, LLC
- RA Capital Management, L.P.
- Stonepine Capital Management
- Cormorant Asset Management LP
- DAFNA Capital Management LLC
- Paradigm Biocapital Advisors LP
- Rosalind Advisors
- Orbimed Advisors LLC
- Darwin Global Management
- Baker Bros Advisors
- TCG Crossover Management, LLC
- Acuta Capital Partners
- Artia Global Parners
- BVF Inc
- Commodore Capital
- Deep Track Capital
- Deerfield Management
- Logos Capital
- BioImpact Capital
- OpalEye Management
- Tang Capital Management
- Eagle Health Investments LP
- Versant Venture Management, LLC
- Squadron Capital Management LLC
- Stempoint Capital LP

## Installation

1. Install Python 3.8 or higher
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Interactive Mode

Run the tracker interactively:

```bash
python biotech_13f_tracker.py
```

You'll see a menu with options:
1. Get latest filings summary for all funds
2. Get detailed holdings for a specific fund
3. Get holdings for ALL funds
4. Analyze holdings overlap across all funds
5. Find stocks with highest total value held
6. Generate full summary report
7. Calculate AUM for all funds
8. Exit

### Command-Line Usage

Quick access to key features:

```bash
# Get latest filings for all funds
python run.py summary

# Get holdings for a specific fund
python run.py holdings "RA Capital Management, L.P."

# Find stocks held by 5+ funds
python run.py overlap 5

# Top stocks by total value held
python run.py topvalue

# Export to Excel
python run.py excel

# List all tracked funds
python run.py list
```

### Programmatic Usage

```python
from biotech_13f_tracker import SEC13FTracker

# Initialize tracker
tracker = SEC13FTracker()

# Get latest filings for all funds
filings_df = tracker.get_all_latest_filings()

# Get detailed holdings for a specific fund
holdings = tracker.get_fund_holdings(
    'RA Capital Management, L.P.',
    '0001346824'
)

# Find stocks held by 5+ funds
overlap = tracker.analyze_overlap(min_funds=5)

# Find stocks with highest total value held
top_stocks = tracker.analyze_top_stocks_by_value()
```

## Output Files

All data is saved to the `data/` directory:

- `latest_filings_YYYYMMDD.csv` - Summary of latest filings for all funds
- `{fund_name}_holdings_YYYY-MM-DD.csv` - Detailed holdings for specific funds
- `all_funds_combined_YYYYMMDD.csv` - Combined holdings for all funds
- `fund_aum_YYYYMMDD.csv` - AUM calculations for all funds (value in dollars)
- `holdings_overlap_YYYYMMDD.csv` - Stocks held by multiple funds
- `top_stocks_by_value_YYYYMMDD.csv` - Stocks ranked by total value held

## Data Fields

### Filings Summary
- Fund name
- CIK (SEC identifier)
- Form type (13F-HR or 13F-HR/A)
- Filing date
- Accession number

### Holdings Data
- Company name
- CUSIP (security identifier)
- Value (in dollars)
- Number of shares
- Fund name
- Filing date

### Overlap Analysis
- Company name
- CUSIP
- Number of funds holding
- List of funds
- Total value across all funds
- Total shares across all funds

### Top Value Analysis
- Company name
- CUSIP
- Number of funds holding
- Total value across all funds (largest to smallest)
- Total shares across all funds

### AUM Analysis
- Fund name
- AUM (total value of all holdings in dollars)
- Number of holdings
- Filing date

## Important Notes

### SEC Rate Limits
- The SEC API limits requests to 10 per second
- The tracker automatically handles rate limiting
- Large operations (overlap analysis) may take 5-10 minutes

### Data Accuracy
- 13F filings are required within 45 days of quarter end
- Filings show positions as of the last day of the quarter
- Not all positions may be disclosed (some can be delayed)

### User Agent
You should update the User-Agent header in the script with your contact email:

```python
HEADERS = {
    'User-Agent': 'Biotech 13F Tracker your.email@example.com',
    ...
}
```

## Common Use Cases

### Find High Conviction Ideas
Look for stocks held by 5+ funds - these represent consensus high-conviction positions:

```bash
python run.py overlap 5
```

### Find Stocks with Largest Aggregate Investments
See which biotech stocks have the most total capital deployed:

```bash
python run.py topvalue
```

### Track Specific Fund Changes
Download holdings quarterly to track position changes:

```bash
python run.py holdings "RA Capital Management, L.P."
# Repeat after each quarterly filing season
```

### Monitor Filing Activity
Track which funds have filed recently:

```bash
python run.py summary
```

### Calculate AUM for All Funds
See the total assets under management for each fund (based on holdings value):

```bash
# In interactive mode, select option 7
python biotech_13f_tracker.py
# Then select option 7
```

### Get All Fund Holdings at Once
Download holdings for all 38 funds in one go:

```bash
# In interactive mode, select option 3
python biotech_13f_tracker.py
# Then select option 3
```

## Quarterly Filing Deadlines

13F filings are due 45 days after quarter end:

- Q1 (Mar 31): Due by May 15
- Q2 (Jun 30): Due by Aug 14
- Q3 (Sep 30): Due by Nov 14
- Q4 (Dec 31): Due by Feb 14

## Troubleshooting

### No holdings data retrieved
- The SEC may have changed XML format
- The fund may not have filed yet
- Check the SEC website manually to verify

### Rate limit errors
- Wait a few minutes and try again
- The SEC blocks IPs that exceed rate limits

### Missing funds
- Some funds may file under different CIKs
- Check SEC EDGAR search to verify CIK numbers

## Future Enhancements

Potential additions:
- Historical comparison (quarter-over-quarter changes)
- Position size analysis (% of portfolio)
- Performance tracking (stock returns after fund entry)
- Sector concentration analysis
- Export to Excel with formatting
- Web dashboard interface
- Email alerts for new filings

## License

Free to use for personal investment research.

## Disclaimer

This tool is for informational purposes only. 13F filings are historical and may not reflect current positions. Always do your own research before making investment decisions.
