#!/usr/bin/env python3
"""
Biotech Fund Tracker
Tracks and analyzes 13F filings for specialist biotech funds
"""

import requests
import pandas as pd
from datetime import datetime
import time
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple, Optional
import re

# SEC API rate limit: 10 requests per second
RATE_LIMIT_DELAY = 0.11

# User agent required by SEC
HEADERS = {
    'User-Agent': 'BiotechFundTracker/1.0 (Personal Research; pr124dev@gmail.com)',
    'Accept-Encoding': 'gzip, deflate'
}

# Fund data
FUNDS = {
    'Boxer Capital Management, LLC': '0002018299',
    'Checkpoint Capital': '0001977548',
    'Caligan Partners LP': '0001727492',
    'Octagon Capital Advisors LP': '0001839435',
    'Perceptive Advisors LLC': '0001224962',
    'Exome Asset Management LLC': '0002011932',
    'Avoro Capital Advisors LLC': '0001633313',
    'Affinity Asset Advisors, LLC': '0001773195',
    'ADAR1 Capital Management, LLC': '0001940272',
    'Saturn V Capital Management LP': '0001964437',
    'Greatpoint Partners': '0001281446',
    'Vestal Point Capital, LP': '0001974915',
    'RTW Investments, LP': '0001493215',
    'Soleus Capital Management, L.P.': '0001802630',
    'Ally Bridge Group (NY) LLC': '0001822947',
    'Ikarian Capital, LLC': '0001778253',
    'RA Capital Management, L.P.': '0001346824',
    'Stonepine Capital Management': '0001440771',
    'Cormorant Asset Management LP': '0001583977',
    'DAFNA Capital Management LLC': '0001389933',
    'Paradigm Biocapital Advisors LP': '0001855655',
    'Rosalind Advisors': '0001622627',
    'Orbimed Advisors LLC': '0001055951',
    'Darwin Global Management': '0001839209',
    'Baker Bros Advisors': '0001263508',
    'TCG Crossover Management, LLC': '0001839948',
    'Acuta Capital Partners': '0001582844',
    'Artia Global Partners': '0001937964',
    'BVF Inc': '0001056807',
    'Commodore Capital': '0001831942',
    'Deep Track Capital': '0001856083',
    'Deerfield Management': '0001009258',
    'Logos Capital': '0001792126',
    'BioImpact Capital': '0001687078',
    'OpalEye Management': '0001595855',
    'Tang Capital Management': '0001232621',
    'Eagle Health Investments LP': '0001842545',
    'Versant Venture Management, LLC': '0001560009',
    'Squadron Capital Management LLC': '0002050709',
    'Stempoint Capital LP': '0001952142',
}


class SEC13FTracker:
    """Tracker for 13F filings from biotech specialist funds"""

    def __init__(self, output_dir: str = 'data'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def get_recent_filings(self, cik: str, fund_name: str, count: int = 5) -> List[Dict]:
        """Get recent 13F-HR filings for a given CIK"""
        # Ensure CIK is padded to 10 digits for the API
        cik_clean = cik.zfill(10)

        url = f'https://data.sec.gov/submissions/CIK{cik_clean}.json'

        try:
            time.sleep(RATE_LIMIT_DELAY)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            filings = []
            recent_filings = data.get('filings', {}).get('recent', {})

            if not recent_filings:
                print(f"  No filings found for {fund_name}")
                return []

            # Find 13F-HR filings
            for i in range(len(recent_filings.get('form', []))):
                form_type = recent_filings['form'][i]
                if form_type in ['13F-HR', '13F-HR/A']:
                    filing_date = recent_filings['filingDate'][i]
                    accession_number = recent_filings['accessionNumber'][i]
                    primary_document = recent_filings['primaryDocument'][i]

                    filings.append({
                        'fund_name': fund_name,
                        'cik': cik,
                        'form_type': form_type,
                        'filing_date': filing_date,
                        'accession_number': accession_number,
                        'primary_document': primary_document
                    })

                    if len(filings) >= count:
                        break

            return filings

        except requests.exceptions.RequestException as e:
            print(f"  Error fetching filings for {fund_name}: {e}")
            return []

    def parse_13f_xml(self, accession_number: str, cik: str, primary_document: Optional[str] = None) -> pd.DataFrame:
        """Parse 13F-HR XML filing to extract holdings"""
        # Format: 0001346824-24-000008 -> 0001346824/24/000008
        acc_no_formatted = accession_number.replace('-', '', 1).replace('-', '/')

        # Try to find the information table XML
        url = f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&dateb=&owner=exclude&count=100'

        # Direct approach: try the primary document (if provided) then common XML filename patterns
        base_url = f'https://www.sec.gov/Archives/edgar/data/{cik.lstrip("0")}/{accession_number.replace("-", "")}'

        xml_patterns = [
            'infotable.xml',
            'form13fInfoTable.xml',
            'primary_doc.xml',
            'informationtable.xml',
            'Form13FInfoTable.xml',
            'InfoTable.xml',
            'InformationTable.xml',
            'xml_filing.xml'
        ]

        holdings = []
        # Try primary document first if available
        tried_urls = []
        primary_dir = None
        if primary_document and '/' in primary_document:
            primary_dir = primary_document.rsplit('/', 1)[0]

        if primary_document:
            try:
                primary_url = f'{base_url}/{primary_document}'
                tried_urls.append(primary_url)
                time.sleep(RATE_LIMIT_DELAY)
                response = self.session.get(primary_url, timeout=30)

                if response.status_code == 200:
                    # Try parsing directly; if the primary document contains embedded infoTable blocks
                    # attempt to extract them
                    try:
                        root = ET.fromstring(response.content)
                    except Exception:
                        text = response.text
                        # find an infoTable or informationTable block and wrap in a root
                        m_start = None
                        for tag in ('<informationTable', '<infoTable'):
                            idx = text.find(tag)
                            if idx != -1:
                                m_start = idx
                                break

                        if m_start is not None:
                            # attempt to find the closing tag
                            end_tag = '</informationTable>' if '<informationTable' in text[m_start:m_start+20] else '</infoTable>'
                            m_end = text.rfind(end_tag)
                            if m_end != -1:
                                extract = text[m_start:m_end+len(end_tag)]
                                wrapped = f'<root>{extract}</root>'
                                try:
                                    root = ET.fromstring(wrapped)
                                except Exception:
                                    root = None
                            else:
                                root = None
                        else:
                            root = None

                    if root is not None:
                        namespaces = {
                            'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable',
                            'ns2': 'http://www.sec.gov/edgar/common'
                        }

                        info_tables = root.findall('.//ns:infoTable', namespaces)
                        if not info_tables:
                            info_tables = root.findall('.//infoTable')
                        
                        # Fallback: find any tag ending in infoTable (ignoring namespace)
                        if not info_tables:
                            info_tables = [el for el in root.iter() if el.tag.endswith('infoTable') or el.tag.endswith('informationTable')]

                        for info_table in info_tables:
                            holding = self._parse_holding_entry(info_table, namespaces)
                            if holding:
                                holdings.append(holding)

                        if holdings:
                            return pd.DataFrame(holdings)
            except Exception:
                # continue to other patterns
                pass

        # Try to use the filing's index.json to discover files in the accession folder
        try:
            index_url = f'{base_url}/index.json'
            tried_urls.append(index_url)
            time.sleep(RATE_LIMIT_DELAY)
            idx_resp = self.session.get(index_url, timeout=30)
            if idx_resp.status_code == 200:
                try:
                    idx_json = idx_resp.json()
                    candidates = []

                    # Preferred method: Find XML file with "INFORMATION TABLE" description
                    if 'filing' in idx_json and 'document_format_files' in idx_json['filing']:
                        for doc in idx_json['filing']['document_format_files']:
                            desc = doc.get('description', '').upper()
                            doc_url = doc.get('document_url', '')
                            if 'INFORMATION TABLE' in desc and doc_url.endswith('.xml'):
                                candidates.append(doc_url)

                    # Fallback method: Collect all files and filter by keywords or .xml extension
                    if not candidates:
                        all_files = []
                        # Handles {'directory': {'item': [...]}} structure
                        if 'directory' in idx_json and 'item' in idx_json['directory']:
                            all_files = [item.get('name') for item in idx_json['directory']['item'] if item.get('name')]

                        # Generic traversal to find all filenames as a last resort
                        if not all_files:
                            def collect_filenames(obj):
                                found_files = []
                                if isinstance(obj, dict):
                                    for k, v in obj.items():
                                        if k in ('name', 'document_url') and isinstance(v, str):
                                            found_files.append(v)
                                        else:
                                            found_files.extend(collect_filenames(v))
                                elif isinstance(obj, list):
                                    for item in obj:
                                        found_files.extend(collect_filenames(item))
                                return list(set(found_files))
                            all_files = collect_filenames(idx_json)

                        # Filter collected files to find likely candidates
                        # Add 'inftab' for cases like 'affinity.inftab.xml'
                        keyword_candidates = [f for f in all_files if any(x in f.lower() for x in ('infotable', 'inftab', 'form13f', 'informationtable', 'info_table', 'xml_filing'))]
                        # As a last resort, try any other XML file in the submission
                        xml_candidates = [f for f in all_files if f.endswith('.xml') and f not in keyword_candidates]
                        candidates.extend(keyword_candidates)
                        candidates.extend(xml_candidates)

                    if candidates:
                        for cand in candidates:
                            try:
                                cand_url = f'{base_url}/{cand}'
                                tried_urls.append(cand_url)
                                time.sleep(RATE_LIMIT_DELAY)
                                r = self.session.get(cand_url, timeout=30)
                                if r.status_code == 200:
                                    try:
                                        root = ET.fromstring(r.content)
                                    except Exception:
                                        # attempt to extract xml block from text
                                        text = r.text
                                        m_start = None
                                        for tag in ('<informationTable', '<infoTable'):
                                            idx = text.find(tag)
                                            if idx != -1:
                                                m_start = idx
                                                break

                                        if m_start is not None:
                                            end_tag = '</informationTable>' if '<informationTable' in text[m_start:m_start+20] else '</infoTable>'
                                            m_end = text.rfind(end_tag)
                                            if m_end != -1:
                                                extract = text[m_start:m_end+len(end_tag)]
                                                wrapped = f'<root>{extract}</root>'
                                                try:
                                                    root = ET.fromstring(wrapped)
                                                except Exception:
                                                    root = None
                                            else:
                                                root = None
                                        else:
                                            root = None

                                    if root is None:
                                        continue

                                    namespaces = {
                                        'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable',
                                        'ns2': 'http://www.sec.gov/edgar/common'
                                    }

                                    info_tables = root.findall('.//ns:infoTable', namespaces)
                                    if not info_tables:
                                        info_tables = root.findall('.//infoTable')
                                    
                                    # Fallback: find any tag ending in infoTable
                                    if not info_tables:
                                        info_tables = [el for el in root.iter() if el.tag.endswith('infoTable') or el.tag.endswith('informationTable')]

                                    for info_table in info_tables:
                                        holding = self._parse_holding_entry(info_table, namespaces)
                                        if holding:
                                            holdings.append(holding)

                                    if holdings: return pd.DataFrame(holdings)
                            except Exception:
                                continue
                except Exception:
                    pass
        except Exception:
            pass

        # Extend patterns to try files that may be located in the same folder
        patterns_to_try = list(xml_patterns)
        if primary_dir:
            patterns_to_try += [f'{primary_dir}/{p}' for p in xml_patterns]

        for pattern in patterns_to_try:
            try:
                xml_url = f'{base_url}/{pattern}'
                tried_urls.append(xml_url)
                time.sleep(RATE_LIMIT_DELAY)
                response = self.session.get(xml_url, timeout=30)

                if response.status_code == 200:
                    # Parse XML
                    try:
                        root = ET.fromstring(response.content)
                    except Exception:
                        # fallback: try to extract infoTable blocks from text content
                        text = response.text
                        m_start = None
                        for tag in ('<informationTable', '<infoTable'):
                            idx = text.find(tag)
                            if idx != -1:
                                m_start = idx
                                break

                        if m_start is not None:
                            end_tag = '</informationTable>' if '<informationTable' in text[m_start:m_start+20] else '</infoTable>'
                            m_end = text.rfind(end_tag)
                            if m_end != -1:
                                extract = text[m_start:m_end+len(end_tag)]
                                wrapped = f'<root>{extract}</root>'
                                try:
                                    root = ET.fromstring(wrapped)
                                except Exception:
                                    root = None
                            else:
                                root = None
                        else:
                            root = None

                    if root is None:
                        continue

                    # Handle different XML namespace formats
                    namespaces = {
                        'ns': 'http://www.sec.gov/edgar/document/thirteenf/informationtable',
                        'ns2': 'http://www.sec.gov/edgar/common'
                    }

                    # Try to find infoTable entries
                    info_tables = root.findall('.//ns:infoTable', namespaces)
                    if not info_tables:
                        info_tables = root.findall('.//infoTable')
                    
                    # Fallback: find any tag ending in infoTable
                    if not info_tables:
                        info_tables = [el for el in root.iter() if el.tag.endswith('infoTable') or el.tag.endswith('informationTable')]

                    for info_table in info_tables:
                        holding = self._parse_holding_entry(info_table, namespaces)
                        if holding:
                            holdings.append(holding)

                    if holdings:
                        break

            except Exception as e:
                continue

        if holdings:
            return pd.DataFrame(holdings)
        else:
            # Debug: show URLs attempted to help diagnose missing infoTable
            try:
                if tried_urls:
                    print(f"  Tried URLs for accession {accession_number}: ")
                    for u in tried_urls:
                        print(f"    {u}")
            except Exception:
                pass

            return pd.DataFrame()

    def _parse_holding_entry(self, info_table: ET.Element, namespaces: Dict) -> Optional[Dict]:
        """Parse a single holding entry from XML"""
        try:
            def get_text(elem, tag_name):
                # Try namespace first
                val = elem.find(f'.//ns:{tag_name}', namespaces)
                if val is not None: return val.text
                
                # Try no namespace
                val = elem.find(f'.//{tag_name}')
                if val is not None: return val.text
                
                # Try fuzzy match (ignoring namespace)
                for child in elem.iter():
                    if child.tag.endswith(tag_name):
                        return child.text
                return None

            name = get_text(info_table, 'nameOfIssuer')
            cusip = get_text(info_table, 'cusip')
            value_text = get_text(info_table, 'value')
            shares_text = get_text(info_table, 'sshPrnamt')

            holding = {
                'name': name if name else '',
                'cusip': cusip if cusip else '',
                'value': int(value_text) * 1000 if value_text else 0,
                'shares': int(shares_text) if shares_text else 0
            }

            return holding

        except Exception as e:
            return None

    def get_all_latest_filings(self) -> pd.DataFrame:
        """Get the most recent 13F filing for all funds"""
        all_filings = []

        print(f"Fetching latest 13F filings for {len(FUNDS)} funds...")
        print("-" * 80)

        for fund_name, cik in FUNDS.items():
            print(f"Processing: {fund_name} (CIK: {cik})")

            filings = self.get_recent_filings(cik, fund_name, count=1)

            if filings:
                latest = filings[0]
                all_filings.append(latest)
                print(f"  Found: {latest['form_type']} filed on {latest['filing_date']}")
            else:
                print(f"  No 13F filings found")

            print()

        df = pd.DataFrame(all_filings)

        if not df.empty:
            # Save to CSV
            output_file = self.output_dir / f'latest_filings_{datetime.now().strftime("%Y%m%d")}.csv'
            try:
                df.to_csv(output_file, index=False)
                print(f"\nSaved filings summary to: {output_file}")
            except PermissionError:
                print(f"\nNote: Could not save to {output_file} (file in use)")

        return df

    def get_fund_holdings(self, fund_name: str, cik: str) -> pd.DataFrame:
        """Get detailed holdings for a specific fund's latest 13F"""
        print(f"Fetching holdings for {fund_name}...")

        filings = self.get_recent_filings(cik, fund_name, count=1)

        if not filings:
            print(f"No filings found for {fund_name}")
            return pd.DataFrame()

        latest = filings[0]
        print(f"Parsing {latest['form_type']} filed on {latest['filing_date']}...")

        holdings = self.parse_13f_xml(latest['accession_number'], cik, latest.get('primary_document'))

        if not holdings.empty:
            holdings['fund_name'] = fund_name
            holdings['filing_date'] = latest['filing_date']

            # Sort by value
            holdings = holdings.sort_values('value', ascending=False)

            # Save to CSV
            safe_name = re.sub(r'[^\w\s-]', '', fund_name).replace(' ', '_')
            output_file = self.output_dir / f'{safe_name}_holdings_{latest["filing_date"]}.csv'
            holdings.to_csv(output_file, index=False)
            print(f"Saved {len(holdings)} holdings to: {output_file}")

        return holdings

    def analyze_overlap(self, min_funds: int = 3) -> pd.DataFrame:
        """Find stocks held by multiple funds"""
        print(f"\nAnalyzing holdings overlap across all funds...")
        print("This may take several minutes...")
        print("-" * 80)

        all_holdings = []

        for fund_name, cik in FUNDS.items():
            holdings = self.get_fund_holdings(fund_name, cik)
            if not holdings.empty:
                all_holdings.append(holdings)
            time.sleep(RATE_LIMIT_DELAY * 2)  # Extra delay between funds

        if not all_holdings:
            print("No holdings data retrieved")
            return pd.DataFrame()

        # Combine all holdings
        combined = pd.concat(all_holdings, ignore_index=True)

        # Analyze overlap by CUSIP
        overlap = combined.groupby('cusip').agg({
            'name': 'first',
            'fund_name': lambda x: list(x),
            'value': 'sum',
            'shares': 'sum'
        }).reset_index()

        overlap['num_funds'] = overlap['fund_name'].apply(len)
        overlap = overlap[overlap['num_funds'] >= min_funds]
        overlap = overlap.sort_values('num_funds', ascending=False)

        # Save results
        output_file = self.output_dir / f'holdings_overlap_{datetime.now().strftime("%Y%m%d")}.csv'
        overlap.to_csv(output_file, index=False)
        print(f"\nFound {len(overlap)} stocks held by {min_funds}+ funds")
        print(f"Saved overlap analysis to: {output_file}")

        return overlap

    def analyze_top_stocks_by_value(self) -> pd.DataFrame:
        """Find stocks held with highest total value across all funds"""
        print(f"\nAnalyzing top stocks by total value held...")
        print("This may take several minutes...")
        print("-" * 80)

        all_holdings = []

        for fund_name, cik in FUNDS.items():
            holdings = self.get_fund_holdings(fund_name, cik)
            if not holdings.empty:
                all_holdings.append(holdings)
            time.sleep(RATE_LIMIT_DELAY * 2)  # Extra delay between funds

        if not all_holdings:
            print("No holdings data retrieved")
            return pd.DataFrame()

        # Combine all holdings
        combined = pd.concat(all_holdings, ignore_index=True)

        # Analyze by stock (CUSIP)
        top_stocks = combined.groupby('cusip').agg({
            'name': 'first',
            'fund_name': lambda x: list(set(x)),  # unique funds holding it
            'value': 'sum',
            'shares': 'sum'
        }).reset_index()

        top_stocks['num_funds'] = top_stocks['fund_name'].apply(len)
        top_stocks = top_stocks.sort_values('value', ascending=False)

        # Save results
        output_file = self.output_dir / f'top_stocks_by_value_{datetime.now().strftime("%Y%m%d")}.csv'
        top_stocks.to_csv(output_file, index=False)
        print(f"\nFound {len(top_stocks)} unique stocks across all portfolios")
        print(f"Saved top stocks analysis to: {output_file}")

        return top_stocks

    def generate_summary_report(self):
        """Generate a summary report of all funds"""
        df = self.get_all_latest_filings()

        if df.empty:
            print("No data to generate report")
            return

        print("\n" + "=" * 80)
        print("BIOTECH FUND TRACKER - SUMMARY REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Total Funds Tracked: {len(FUNDS)}")
        print(f"Funds with Recent 13F Filings: {len(df)}")
        print("\nMost Recent Filing Dates:")

        if not df.empty and 'filing_date' in df.columns:
            # Sort by filing_date descending and get top 10
            df_sorted = df.sort_values('filing_date', ascending=False).head(10)
            print(df_sorted[['fund_name', 'filing_date', 'form_type']].to_string(index=False))

        print("\n" + "=" * 80)

    def generate_full_summary_report(self):
        """Generate a comprehensive summary report with filings, holdings, and AUM for all funds"""
        print(f"\n{'=' * 80}")
        print("GENERATING FULL SUMMARY REPORT")
        print("=" * 80)
        print("This will fetch all filings, holdings, and calculate AUM for all funds...")
        print("This may take several minutes...")
        print("-" * 80)

        # Step 1: Get all latest filings to know filing dates
        print("\nStep 1: Getting filing dates for all funds...")
        filings_dict = {}
        for fund_name, cik in FUNDS.items():
            filings = self.get_recent_filings(cik, fund_name, count=1)
            if filings:
                filings_dict[fund_name] = {
                    'filing_date': filings[0]['filing_date'],
                    'form_type': filings[0]['form_type'],
                    'accession_number': filings[0]['accession_number']
                }
            time.sleep(RATE_LIMIT_DELAY)

        # Step 2: Get all holdings and create data with holdings as columns
        print("\nStep 2: Fetching all holdings and calculating AUM...")
        fund_data = []
        all_aum = []

        for fund_name, cik in FUNDS.items():
            print(f"Processing: {fund_name}")
            
            # Get holdings
            holdings = self.get_fund_holdings(fund_name, cik)
            
            # Get filing date
            filing_date = filings_dict.get(fund_name, {}).get('filing_date', 'N/A')
            
            if not holdings.empty:
                # Sort by value descending (highest holdings first)
                holdings = holdings.sort_values('value', ascending=False)
                
                # Calculate AUM for this fund
                total_value = holdings['value'].sum()
                stock_names = holdings['name'].tolist()
                
                all_aum.append({
                    'fund_name': fund_name,
                    'cik': cik,
                    'aum': total_value,
                    'num_holdings': len(holdings),
                    'filing_date': filing_date
                })
            else:
                total_value = 0
                stock_names = []
                all_aum.append({
                    'fund_name': fund_name,
                    'cik': cik,
                    'aum': 0,
                    'num_holdings': 0,
                    'filing_date': filing_date
                })
            
            # Create row with fund info and all holdings as columns
            row_data = {
                'fund_name': fund_name,
                'filing_date': filing_date,
                'aum': total_value
            }
            
            # Add each stock as a column (holding_1, holding_2, etc.)
            for i, stock in enumerate(stock_names, 1):
                row_data[f'holding_{i}'] = stock
            
            fund_data.append(row_data)
            
            time.sleep(RATE_LIMIT_DELAY * 2)
            print()

        # Create DataFrames
        aum_df = pd.DataFrame(all_aum)
        aum_df = aum_df.sort_values('aum', ascending=False)

        # Step 3: Save comprehensive CSV with format: fund | filing_date | AUM | holdings as columns
        df = pd.DataFrame(fund_data)
        
        # Save combined file with all data
        output_file = self.output_dir / f'complete_summary_{datetime.now().strftime("%Y%m%d")}.csv'
        try:
            df.to_csv(output_file, index=False)
            print(f"\nSaved complete summary to: {output_file}")
        except PermissionError:
            print(f"\nNote: Could not save to {output_file} (file in use)")

        # Save AUM data
        aum_file = self.output_dir / f'fund_aum_{datetime.now().strftime("%Y%m%d")}.csv'
        try:
            aum_df.to_csv(aum_file, index=False)
            print(f"Saved AUM data to: {aum_file}")
        except PermissionError:
            print(f"Note: Could not save to {aum_file} (file in use)")

        # Display summary
        print("\n" + "=" * 80)
        print("FULL SUMMARY REPORT")
        print("=" * 80)
        print(f"Total Funds Tracked: {len(FUNDS)}")
        print(f"Funds with Filings: {len(filings_dict)}")
        
        if not aum_df.empty:
            total_aum = aum_df['aum'].sum()
            total_aum_billions = total_aum / 1_000_000_000
            print(f"Total AUM (all funds): ${total_aum_billions:,.1f}B")
        
        print("\n" + "-" * 80)
        print("Top 10 Funds by AUM:")
        print("-" * 80)
        print(f"{'Rank':<5} {'Fund Name':<35} {'Filing Date':<12} {'AUM':>12} {'Holdings':>10}")
        print("-" * 80)
        
        if not aum_df.empty:
            for rank, (idx, row) in enumerate(aum_df.head(10).iterrows(), 1):
                fund_name = row['fund_name'][:33] if len(row['fund_name']) > 33 else row['fund_name']
                filing_date = str(row['filing_date'])[:10] if row['filing_date'] else 'N/A'
                aum_billions = row['aum'] / 1_000_000_000
                print(f"{rank:<5} {fund_name:<35} {filing_date:<12} ${aum_billions:>10.1f}B {int(row['num_holdings']):>10}")
        
        print("=" * 80)
        print("\nFiles saved:")
        print(f"  - Complete summary (fund | filing_date | AUM | holdings as columns): {output_file}")
        print(f"  - AUM data: {aum_file}")
        print("=" * 80)

    def calculate_fund_aum(self, fund_name: str, cik: str) -> Dict:
        """Calculate AUM for a specific fund by summing all holding values"""
        print(f"\nCalculating AUM for {fund_name}...")

        holdings = self.get_fund_holdings(fund_name, cik)

        if holdings.empty:
            return {'fund_name': fund_name, 'aum': 0, 'num_holdings': 0, 'filing_date': None}

        # Sum all values (value is already in dollars from _parse_holding_entry)
        total_value = holdings['value'].sum()
        num_holdings = len(holdings)
        filing_date = holdings['filing_date'].iloc[0] if 'filing_date' in holdings.columns else None

        aum_info = {
            'fund_name': fund_name,
            'aum': total_value,
            'num_holdings': num_holdings,
            'filing_date': filing_date
        }

        print(f"  AUM: ${total_value:,.0f}")
        print(f"  Holdings: {num_holdings}")

        return aum_info

    def get_all_funds_holdings(self) -> pd.DataFrame:
        """Get holdings for all funds and save to a combined file with funds as rows"""
        print(f"\n{'=' * 80}")
        print("FETCHING HOLDINGS FOR ALL FUNDS")
        print("=" * 80)
        print("This will fetch and save holdings for all funds...")
        print("This may take several minutes...")
        print("-" * 80)

        fund_data = []
        
        # First, get latest filings to know filing dates
        print("\nGetting filing dates...")
        filings_dict = {}
        for fund_name, cik in FUNDS.items():
            filings = self.get_recent_filings(cik, fund_name, count=1)
            if filings:
                filings_dict[fund_name] = {
                    'filing_date': filings[0]['filing_date'],
                    'form_type': filings[0]['form_type']
                }
            time.sleep(RATE_LIMIT_DELAY)
        
        # Now get holdings for each fund
        for fund_name, cik in FUNDS.items():
            print(f"Processing: {fund_name}")
            holdings = self.get_fund_holdings(fund_name, cik)
            
            # Get filing date
            filing_date = filings_dict.get(fund_name, {}).get('filing_date', 'N/A')
            
            if not holdings.empty:
                # Sort by value descending (highest holdings first)
                holdings = holdings.sort_values('value', ascending=False)
                
                # Calculate AUM for this fund
                aum = holdings['value'].sum()
                
                # Get list of stock names
                stock_names = holdings['name'].tolist()
            else:
                aum = 0
                stock_names = []
            
            # Create row with fund info and all holdings as columns
            row_data = {
                'fund_name': fund_name,
                'filing_date': filing_date,
                'aum': aum
            }
            
            # Add each stock as a column (holding_1, holding_2, etc.)
            for i, stock in enumerate(stock_names, 1):
                row_data[f'holding_{i}'] = stock
            
            fund_data.append(row_data)
            
            time.sleep(RATE_LIMIT_DELAY * 2)
            print()

        if not fund_data:
            print("No holdings data retrieved")
            return pd.DataFrame()

        # Create DataFrame
        df = pd.DataFrame(fund_data)

        # Save to CSV
        output_file = self.output_dir / f'all_funds_combined_{datetime.now().strftime("%Y%m%d")}.csv'
        try:
            df.to_csv(output_file, index=False)
            print(f"\nSaved {len(df)} funds to: {output_file}")
        except PermissionError:
            print(f"\nNote: Could not save to {output_file} (file in use)")

        # Display summary
        print("\n" + "=" * 80)
        print("HOLDINGS SUMMARY")
        print("=" * 80)
        print(f"{'Fund Name':<45} {'Filing Date':<12} {'AUM':>12} {'# Holdings':>10}")
        print("-" * 80)
        
        for _, row in df.iterrows():
            aum_b = row['aum'] / 1_000_000_000
            num_holdings = sum(1 for col in df.columns if col.startswith('holding_'))
            print(f"{row['fund_name']:<45} {row['filing_date']:<12} ${aum_b:>10.1f}B {num_holdings:>10}")
        
        print("=" * 80)
        
        return df

    def get_all_funds_aum(self) -> pd.DataFrame:
        """Calculate and display AUM for all funds"""
        print(f"\n{'=' * 80}")
        print("CALCULATING AUM FOR ALL FUNDS")
        print("=" * 80)
        print("This will fetch holdings for all funds and calculate AUM...")
        print("This may take several minutes...")
        print("-" * 80)

        all_aum = []

        for fund_name, cik in FUNDS.items():
            print(f"Processing: {fund_name}")
            aum_info = self.calculate_fund_aum(fund_name, cik)
            all_aum.append(aum_info)
            time.sleep(RATE_LIMIT_DELAY * 2)  # Extra delay between funds
            print()

        # Create DataFrame
        df = pd.DataFrame(all_aum)

        if not df.empty:
            # Sort by AUM descending
            df = df.sort_values('aum', ascending=False)

            # Add formatted AUM column
            df['aum_formatted'] = df['aum'].apply(lambda x: f"${x:,.0f}")

            print("\n" + "=" * 80)
            print("AUM (ASSETS UNDER MANAGEMENT) - ALL FUNDS")
            print("=" * 80)
            print(f"{'Rank':<5} {'Fund Name':<45} {'AUM':>15} {'Holdings':>10}")
            print("-" * 80)

            # Reset index to get proper ranking
            df_display = df.reset_index(drop=True)
            for rank, (idx, row) in enumerate(df_display.iterrows(), 1):
                fund_name = row['fund_name'][:43] if len(row['fund_name']) > 43 else row['fund_name']
                aum_billions = row['aum'] / 1_000_000_000
                aum_str = f"${aum_billions:,.1f}B"
                print(f"{rank:<5} {fund_name:<45} {aum_str:>15} {row['num_holdings']:>10}")

            # Summary statistics
            total_aum = df['aum'].sum()
            total_aum_billions = total_aum / 1_000_000_000
            avg_aum_billions = total_aum_billions / len(df)
            print("-" * 80)
            print(f"{'TOTAL AUM:':<52} ${total_aum_billions:,.1f}B")
            print(f"{'Average AUM per fund:':<52} ${avg_aum_billions:,.1f}B")
            print("=" * 80)

            # Save to CSV
            output_file = self.output_dir / f'fund_aum_{datetime.now().strftime("%Y%m%d")}.csv'
            try:
                df.to_csv(output_file, index=False)
                print(f"\nSaved AUM data to: {output_file}")
            except PermissionError:
                print(f"\nNote: Could not save to {output_file} (file in use)")

        return df


def print_menu():
    """Print the main menu options"""
    print("\n" + "=" * 80)
    print("BIOTECH FUND TRACKER")
    print("=" * 80)
    print("\nOptions:")
    print("1. Get latest filings summary for all funds")
    print("2. Get detailed holdings for a specific fund")
    print("3. Get holdings for ALL funds")
    print("4. Analyze holdings overlap across all funds")
    print("5. Find stocks with highest total value held")
    print("6. Calculate AUM for all funds")
    print("7. Generate full summary report (all data)")
    print("8. Exit")

def main():
    """Main entry point"""
    tracker = SEC13FTracker()

    print_menu()

    while True:
        choice = input("\nSelect option (1-8): ").strip()

        if choice == '1':
            tracker.get_all_latest_filings()

        elif choice == '2':
            print("\nAvailable funds:")
            for i, fund_name in enumerate(FUNDS.keys(), 1):
                print(f"{i}. {fund_name}")

            try:
                fund_idx = int(input("\nSelect fund number: ")) - 1
                fund_name = list(FUNDS.keys())[fund_idx]
                cik = FUNDS[fund_name]
                tracker.get_fund_holdings(fund_name, cik)
            except (ValueError, IndexError):
                print("Invalid selection")

        elif choice == '3':
            tracker.get_all_funds_holdings()

        elif choice == '4':
            min_funds = input("Minimum number of funds holding stock (default 3): ").strip()
            min_funds = int(min_funds) if min_funds else 3
            tracker.analyze_overlap(min_funds=min_funds)

        elif choice == '5':
            tracker.analyze_top_stocks_by_value()

        elif choice == '6':
            tracker.get_all_funds_aum()

        elif choice == '7':
            tracker.generate_full_summary_report()

        elif choice == '8':
            print("Exiting...")
            break

        else:
            print("Invalid option")
        
        # Show menu again after each command (except exit)
        if choice != '8':
            print_menu()


if __name__ == '__main__':
    main()
