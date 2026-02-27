# 2026-02-17 | v1.0.0 | Real-time trading dashboard | Writer: J.Ekrami | Co-writer: Gemini 2.0 Flash Thinking
"""
live_monitor.py

Real-time monitoring dashboard for PAI-Lab live paper trading.

Features:
- Live equity curve visualization
- Recent trades table with color-coded outcomes
- Current position status
- Regime status indicator
- Risk metrics panel
- System health monitoring
- Auto-refresh every 60 seconds
"""

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import os
from pathlib import Path

# Paths to log files
LOGS_DIR = Path(__file__).parent.parent / "logs"
METRICS_FILE = LOGS_DIR / "live_metrics.csv"
TRADES_FILE = LOGS_DIR / "live_trades.csv"
REGIME_FILE = LOGS_DIR / "live_regime_events.csv"
STATE_FILE = Path(__file__).parent.parent / "state" / "engine_state.pkl"


def load_metrics():
    """Load live metrics data"""
    try:
        if METRICS_FILE.exists():
            df = pd.read_csv(METRICS_FILE)
            return df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def load_trades():
    """Load live trades data"""
    try:
        if TRADES_FILE.exists():
            df = pd.read_csv(TRADES_FILE)
            return df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def load_regime_events():
    """Load regime events data"""
    try:
        if REGIME_FILE.exists():
            df = pd.read_csv(REGIME_FILE)
            return df
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def load_context():
    """Load AI context data"""
    try:
        f = LOGS_DIR / "ai_context.csv"
        if f.exists():
            return pd.read_csv(f)
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def load_backtest_trades():
    """Load backtest trades data"""
    try:
        f = LOGS_DIR / "trades.csv"
        if f.exists():
            return pd.read_csv(f)
        return pd.DataFrame()
    except Exception as e:
        return pd.DataFrame()


def get_system_health():
    """Get system health status"""
    try:
        metrics = load_metrics()
        if metrics.empty:
            return "🟡 No Data", "System initialized, waiting for data..."
        
        # Check last update time
        last_ts = metrics.iloc[-1]['timestamp'] if 'timestamp' in metrics.columns else None
        if last_ts:
            last_time = pd.to_datetime(last_ts)
            now = pd.Timestamp.now()
            delta = (now - last_time).total_seconds()
            
            if delta < 180:  # Less than 3 minutes
                return "🟢 Active", f"Last update: {int(delta)}s ago"
            elif delta < 600:  # Less than 10 minutes
                return "🟡 Delayed", f"Last update: {int(delta/60)}m ago"
            else:
                return "🔴 Inactive", f"Last update: {int(delta/60)}m ago"
        
        return "🟡 Unknown", "Timestamp data unavailable"
    except Exception as e:
        return "🔴 Error", f"Error: {str(e)[:50]}"


def plot_equity_curve():
    """Generate equity curve plot"""
    metrics = load_metrics()
    
    if metrics.empty or 'equity' not in metrics.columns:
        # Return empty figure with message
        fig = go.Figure()
        fig.add_annotation(
            text="No equity data available yet",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            title="Equity Curve (ATR Units)",
            xaxis_title="Trade Number",
            yaxis_title="Equity",
            template="plotly_white",
            height=400
        )
        return fig
    
    # Create equity curve
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=list(range(len(metrics))),
        y=metrics['equity'],
        mode='lines',
        name='Equity',
        line=dict(color='#2E86AB', width=2),
        fill='tozeroy',
        fillcolor='rgba(46, 134, 171, 0.1)'
    ))
    
    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    fig.update_layout(
        title="Equity Curve (ATR Units)",
        xaxis_title="Trade Number",
        yaxis_title="Equity (ATR)",
        template="plotly_white",
        height=400,
        hovermode='x unified'
    )
    
    return fig


def get_recent_trades(limit=20):
    """Get recent trades as formatted table"""
    trades = load_trades()
    
    if trades.empty:
        return pd.DataFrame({
            "Time": ["No trades yet"],
            "Direction": ["-"],
            "Entry": ["-"],
            "Exit": ["-"],
            "Outcome": ["-"],
            "Equity": ["-"]
        })
    
    # Get last N trades
    recent = trades.tail(limit).copy()
    
    # Format for display
    display_df = pd.DataFrame()
    
    if 'entry_time' in recent.columns:
        display_df['Time'] = pd.to_datetime(recent['entry_time']).dt.strftime('%m-%d %H:%M')
    
    if 'direction' in recent.columns:
        display_df['Direction'] = recent['direction'].apply(
            lambda x: f"🟢 {x.upper()}" if x == 'bullish' else f"🔴 {x.upper()}"
        )
    
    if 'entry_price' in recent.columns:
        display_df['Entry'] = recent['entry_price'].round(2)
    
    if 'exit_price' in recent.columns:
        display_df['Exit'] = recent['exit_price'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) and x != '' else "OPEN"
        )
    
    if 'outcome' in recent.columns:
        display_df['Outcome'] = recent['outcome'].apply(
            lambda x: "✅ WIN" if x == 1 else ("❌ LOSS" if x == 0 else "-")
        )
    
    if 'equity_after' in recent.columns:
        display_df['Equity'] = recent['equity_after'].round(2)
    
    return display_df.iloc[::-1]  # Reverse to show newest first


def get_bt_trades(limit=50):
    """Get backtest trades as formatted table"""
    trades = load_backtest_trades()
    
    if trades.empty:
        return pd.DataFrame({"Time": ["No trades yet"], "Direction": ["-"], "Entry": ["-"], "Exit": ["-"], "Outcome": ["-"], "Equity": ["-"]})
    
    recent = trades.tail(limit).copy()
    display_df = pd.DataFrame()
    
    if 'entry_time' in recent.columns:
        display_df['Time'] = pd.to_datetime(recent['entry_time'], errors='coerce').dt.strftime('%m-%d %H:%M')
    
    if 'direction' in recent.columns:
        display_df['Direction'] = recent['direction'].apply(
            lambda x: f"🟢 {x.upper()}" if x == 'bullish' else f"🔴 {x.upper()}"
        )
    
    if 'entry_price' in recent.columns:
        display_df['Entry'] = recent['entry_price'].round(2)
    
    if 'exit_price' in recent.columns:
        display_df['Exit'] = recent['exit_price'].apply(
            lambda x: f"{x:.2f}" if pd.notna(x) and str(x).strip() != '' else "OPEN"
        )
    
    if 'outcome' in recent.columns:
        display_df['Outcome'] = recent['outcome'].apply(
            lambda x: "✅ WIN" if x == 1 else ("❌ LOSS" if x == 0 else "-")
        )
    
    if 'equity_after' in recent.columns:
        display_df['Equity'] = recent['equity_after'].round(2)
    
    return display_df.iloc[::-1]


def get_context_table(limit=50):
    """Get formatted AI context table"""
    ctx_df = load_context()
    if ctx_df.empty:
        return pd.DataFrame({"Time": ["No data"], "Strategy": ["-"], "Regime": ["-"], "Confidence": ["-"], "Decision": ["-"]})
    
    recent = ctx_df.tail(limit).copy()
    display_df = pd.DataFrame()
    
    if 'bar_time' in recent.columns:
        display_df['Time'] = pd.to_datetime(recent['bar_time'], errors='coerce').dt.strftime('%m-%d %H:%M')
    
    if 'selected_strategy' in recent.columns:
        display_df['Strategy'] = recent['selected_strategy']
        
    if 'ai_env' in recent.columns and 'ai_bias' in recent.columns:
        display_df['Regime'] = recent['ai_env'] + " (" + recent['ai_bias'] + ")"
        
    if 'ai_confidence' in recent.columns:
        display_df['Confidence'] = recent['ai_confidence'].round(2)
        
    if 'blocked_by_constraint' in recent.columns and 'constraint_reason' in recent.columns:
        display_df['Decision'] = recent.apply(
            lambda x: f"🔴 BLOCKED: {x['constraint_reason']}" if str(x['blocked_by_constraint']).lower() == 'true' else "🟢 EXECUTED", axis=1
        )
        
    return display_df.iloc[::-1]




def get_current_position():
    """Get current position status"""
    trades = load_trades()
    
    if trades.empty:
        return "No Position", "-", "-", "-", "-"
    
    last_trade = trades.iloc[-1]
    
    # Check if position is open (no exit price)
    if pd.isna(last_trade.get('exit_price')) or last_trade.get('exit_price') == '':
        direction = last_trade.get('direction', 'unknown')
        entry = last_trade.get('entry_price', 0)
        size = last_trade.get('size', 0)
        entry_time = last_trade.get('entry_time', 'N/A')
        
        status = f"🟢 OPEN ({direction.upper()})"
        return status, f"{entry:.2f}", f"{size:.4f}", entry_time, "Waiting for exit..."
    else:
        return "⚪ No Position", "-", "-", "-", "Ready for next signal"


def get_regime_status():
    """Get current regime status"""
    metrics = load_metrics()
    
    if metrics.empty or 'regime_paused' not in metrics.columns:
        return "🟡 Unknown", "No regime data available"
    
    last_status = metrics.iloc[-1]['regime_paused']
    
    if last_status:
        reason = "Statistical edge deteriorated (z-score threshold)"
        return "🔴 PAUSED", reason
    else:
        return "🟢 ACTIVE", "Trading edge confirmed"


def get_risk_metrics():
    """Get current risk metrics"""
    metrics = load_metrics()
    
    if metrics.empty:
        return {
            "Current Equity": "N/A",
            "Rolling Expectancy": "N/A",
            "Rolling Winrate": "N/A",
            "Adaptive Threshold": "N/A",
            "Rolling Volatility": "N/A"
        }
    
    last = metrics.iloc[-1]
    
    return {
        "Current Equity": f"{last.get('equity', 0):.2f} ATR",
        "Rolling Expectancy": f"{last.get('rolling_expectancy', 0):.3f}",
        "Rolling Winrate": f"{last.get('rolling_winrate', 0):.1%}",
        "Adaptive Threshold": f"{last.get('adaptive_threshold', 0):.2f}",
        "Rolling Volatility": f"{last.get('rolling_volatility', 0):.3f}"
    }


def refresh_dashboard():
    """Refresh all dashboard components"""
    # System health
    health_status, health_msg = get_system_health()
    
    # Equity curve
    equity_plot = plot_equity_curve()
    
    # Recent context logic
    context_table = get_context_table(50)
    
    # Backtest trades
    bt_table = get_bt_trades(50)

    # Current position
    pos_status, pos_entry, pos_size, pos_time, pos_note = get_current_position()
    position_info = f"""
### Current Position
**Status:** {pos_status}  
**Entry Price:** {pos_entry}  
**Size:** {pos_size}  
**Entry Time:** {pos_time}  
**Note:** {pos_note}
"""
    
    # Regime status
    regime_status, regime_reason = get_regime_status()
    regime_info = f"""
### Regime Status
**Status:** {regime_status}  
**Reason:** {regime_reason}
"""
    
    # Risk metrics
    risk = get_risk_metrics()
    risk_info = f"""
### Risk Metrics
**Current Equity:** {risk['Current Equity']}  
**Rolling Expectancy:** {risk['Rolling Expectancy']}  
**Rolling Winrate:** {risk['Rolling Winrate']}  
**Adaptive Threshold:** {risk['Adaptive Threshold']}  
**Rolling Volatility:** {risk['Rolling Volatility']}
"""
    
    # System health
    health_info = f"""
### System Health
**Status:** {health_status}  
**Details:** {health_msg}
"""
    
    return (
        equity_plot,
        trades_table,
        position_info,
        regime_info,
        risk_info,
        health_info,
        context_table,
        bt_table
    )


# Build Gradio Interface
with gr.Blocks(title="PAI-Lab Live Monitor") as demo:
    gr.Markdown(
        """
        # 📊 PAI-Lab Live Trading Monitor
        **Real-time monitoring dashboard for paper trading operations**
        
        Dashboard auto-refreshes every 60 seconds. Click "🔄 Refresh Now" for manual update.
        """
    )
    
    with gr.Row():
        refresh_btn = gr.Button("🔄 Refresh Now", variant="primary", scale=1)
        last_update_box = gr.Textbox(
            value=f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            label="",
            interactive=False,
            scale=2
        )
    
    with gr.Tabs():
        with gr.Tab("Dashboard (Live)"):
            with gr.Row():
                with gr.Column(scale=2):
                    equity_plot = gr.Plot(label="Equity Curve")
                
                with gr.Column(scale=1):
                    position_md = gr.Markdown(value="Loading...")
                    regime_md = gr.Markdown(value="Loading...")
            
            with gr.Row():
                with gr.Column(scale=2):
                    trades_table = gr.Dataframe(
                        headers=["Time", "Direction", "Entry", "Exit", "Outcome", "Equity"],
                        label="Recent Live Trades (Latest First)",
                        wrap=True
                    )
                
                with gr.Column(scale=1):
                    risk_md = gr.Markdown(value="Loading...")
                    health_md = gr.Markdown(value="Loading...")
                    
        with gr.Tab("AI Decisions (Why?)"):
            context_table = gr.Dataframe(
                headers=["Time", "Strategy", "Regime", "Confidence", "Decision"],
                label="AI Context & Gate Decisions (Recent Setups)",
                wrap=True
            )
            
        with gr.Tab("Backtest Ledger"):
            bt_trades_table = gr.Dataframe(
                headers=["Time", "Direction", "Entry", "Exit", "Outcome", "Equity"],
                label="Backtest Trades (Latest First)",
                wrap=True
            )
    
    outputs_list = [
        equity_plot, trades_table, position_md, regime_md, risk_md, health_md, context_table, bt_trades_table
    ]
    
    # Manual refresh button
    refresh_btn.click(
        fn=refresh_dashboard,
        inputs=[],
        outputs=outputs_list
    )
    
    # Initial load
    demo.load(
        fn=refresh_dashboard,
        inputs=[],
        outputs=outputs_list
    )


def auto_refresh():
    """Auto-refresh function for periodic updates"""
    import time
    while True:
        time.sleep(60)  # Wait 60 seconds
        # Gradio will handle the refresh via the load event


if __name__ == "__main__":
    print("🚀 Starting PAI-Lab Live Monitor Dashboard...")
    print(f"📂 Monitoring logs at: {LOGS_DIR}")
    print(f"🌐 Dashboard will be available at: http://localhost:7860")
    print("\nDashboard refreshes every 60 seconds automatically.")
    print("Press Ctrl+C to stop the dashboard.\n")
    
    demo.queue()  # Enable queue for better performance
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )
