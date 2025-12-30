"""
Script to analyze competitor strategy from captured activity data.
"""
import pandas as pd
import json
import ast
from datetime import datetime

INPUT_FILE = "analysis/activity_data.csv"
OUTPUT_REPORT = "analysis/competitor_analysis.md"

def parse_df():
    # Load with low_memory=False to handle mixed types
    df = pd.read_csv(INPUT_FILE, low_memory=False)
    
    # Filter for trade rows (rows with transactionHash or type='TRADE')
    # Based on inspection, column 'type' might be 'TRADE' or 'LIQUIDITY' etc.
    # Also rows with 'transactionHash' are trades.
    
    # Let's inspect available columns relevant to trades
    trade_cols = ['timestamp', 'asset', 'title', 'outcome', 'side', 'price', 'size', 'usdcSize', 'transactionHash']
    
    # Create a clean trades dataframe
    trades = df.dropna(subset=['transactionHash']).copy()
    
    # Convert timestamp
    def convert_timestamp(ts):
        try:
            return datetime.fromtimestamp(int(ts))
        except:
            return pd.NaT
            
    if 'timestamp' in trades.columns:
        trades['dt'] = trades['timestamp'].apply(convert_timestamp)
        
    return trades

def analyze_strategy(trades):
    report = []
    report.append("# Competitor Strategy Analysis: Account88888")
    report.append(f"Analysis generated at: {datetime.now()}")
    
    if trades.empty:
        report.append("No trades found in dataset.")
        return "\n".join(report)

    # 1. Frequency Analysis
    report.append("\n## Volume & Frequency")
    total_trades = len(trades)
    min_time = trades['dt'].min()
    max_time = trades['dt'].max()
    duration = (max_time - min_time).total_seconds() / 60 if pd.notnull(max_time) else 0
    
    report.append(f"- Total Trades: {total_trades}")
    report.append(f"- Time Span: {duration:.2f} minutes")
    report.append(f"- Trades/Min: {total_trades/duration:.2f}" if duration > 0 else "- Trades/Min: N/A")

    # 2. Asset Analysis
    report.append("\n## Asset Preference")
    if 'title' in trades.columns:
        top_assets = trades['title'].value_counts().head(5)
        for asset, count in top_assets.items():
            report.append(f"- {asset}: {count} trades")

    # 3. Execution Pattern (Delta Neutral Detection)
    report.append("\n## Execution Strategy Detection")
    # Group by timestamp (to nearest second) to find simultaneous executions
    trades['ts_rounded'] = trades['timestamp'].astype(str).str[:10]  # truncate milliseconds if any
    
    groups = trades.groupby(['ts_rounded', 'title'])
    
    arb_opportunities = 0
    total_groups = 0
    
    report.append("\n### Simultaneous Execution Analysis")
    report.append("| Timestamp | Market | Up Price | Down Price | Total Cost | Spread |")
    report.append("|-----------|--------|----------|------------|------------|--------|")
    
    for (ts, market), group in groups:
        total_groups += 1
        # Check if we have both UP and DOWN buys
        if len(group) >= 2:
            outcomes = group['outcome'].unique()
            if 'Up' in outcomes and 'Down' in outcomes:
                # Calculate average price for UP and DOWN in this second
                up_trades = group[group['outcome'] == 'Up']
                down_trades = group[group['outcome'] == 'Down']
                
                avg_up = up_trades['price'].mean()
                avg_down = down_trades['price'].mean()
                
                total_cost = avg_up + avg_down
                spread = 1.0 - total_cost
                
                if total_cost < 1.0:
                    arb_opportunities += 1
                    status = "**ARBITRAGE**"
                else:
                    status = "Normal/Loss"
                    
                report.append(f"| {ts} | {market[:30]}... | {avg_up:.4f} | {avg_down:.4f} | {total_cost:.4f} | {spread:.4f} ({status}) |")

    report.append(f"\n- Total Paired Executions: {total_groups}")
    report.append(f"- Potentially Profitable Arbs (Cost < 1.0): {arb_opportunities}")
    
    # 4. Profitability Estimates
    # Look for 'percentPnl' if available in the summary rows (not trades)
    # Re-read full DF for non-trade rows
    full_df = pd.read_csv(INPUT_FILE, low_memory=False)
    summary_rows = full_df[full_df['transactionHash'].isna()]
    
    if not summary_rows.empty and 'percentPnl' in summary_rows.columns:
        report.append("\n## Overall Profitability (from Positions)")
        avg_pnl = summary_rows['percentPnl'].mean()
        max_pnl = summary_rows['percentPnl'].max()
        report.append(f"- Average ROI per Position: {avg_pnl:.2f}%")
        report.append(f"- Max ROI: {max_pnl:.2f}%")
        
    return "\n".join(report)

def main():
    try:
        trades = parse_df()
        report_content = analyze_strategy(trades)
        
        with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
            f.write(report_content)
            
        print(f"Analysis complete. Report saved to {OUTPUT_REPORT}")
        print("-" * 50)
        print(report_content)
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
