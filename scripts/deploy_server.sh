#!/bin/bash
# =============================================================================
# TAIL BETTING MONITOR - SERVER DEPLOYMENT SCRIPT
# =============================================================================
# Deploy on Linux server with systemd or cron
#
# Options:
#   1. systemd service (recommended) - runs as daemon
#   2. cron job - runs periodically
#   3. screen/tmux - manual background process
#
# =============================================================================

# Configuration
PROJECT_DIR="/opt/polymarket-bot"
PYTHON_PATH="/opt/polymarket-bot/venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/scripts/scheduled_monitor.py"
LOG_DIR="$PROJECT_DIR/logs"
INTERVAL_MINUTES=30

# =============================================================================
# OPTION 1: SYSTEMD SERVICE (Recommended for production)
# =============================================================================
create_systemd_service() {
    cat > /etc/systemd/system/polymarket-tail-monitor.service << EOF
[Unit]
Description=Polymarket Tail Betting Monitor
After=network.target

[Service]
Type=simple
User=polymarket
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH $SCRIPT_PATH --daemon --interval $INTERVAL_MINUTES
Restart=always
RestartSec=60
StandardOutput=append:$LOG_DIR/service.log
StandardError=append:$LOG_DIR/service.log

[Install]
WantedBy=multi-user.target
EOF

    echo "Systemd service created. To enable:"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable polymarket-tail-monitor"
    echo "  sudo systemctl start polymarket-tail-monitor"
    echo "  sudo systemctl status polymarket-tail-monitor"
}

# =============================================================================
# OPTION 2: CRON JOB
# =============================================================================
create_cron_job() {
    # Run every 30 minutes
    CRON_CMD="*/$INTERVAL_MINUTES * * * * cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_PATH >> $LOG_DIR/cron.log 2>&1"
    
    echo "Add this line to crontab (crontab -e):"
    echo "$CRON_CMD"
}

# =============================================================================
# OPTION 3: SCREEN SESSION
# =============================================================================
start_screen_session() {
    screen -dmS polymarket-monitor bash -c "cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_PATH --daemon --interval $INTERVAL_MINUTES"
    echo "Started in screen session 'polymarket-monitor'"
    echo "To attach: screen -r polymarket-monitor"
    echo "To detach: Ctrl+A, then D"
}

# =============================================================================
# SETUP SCRIPT
# =============================================================================
setup_server() {
    echo "Setting up Polymarket Tail Bot on server..."
    
    # Create directories
    mkdir -p $PROJECT_DIR
    mkdir -p $LOG_DIR
    mkdir -p $PROJECT_DIR/data/tail_bot
    
    # Copy project files (run from local machine)
    echo "Copy project files to server:"
    echo "  scp -r ./* user@server:$PROJECT_DIR/"
    
    # Create virtual environment
    echo "On server, run:"
    echo "  cd $PROJECT_DIR"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install httpx"
    
    # Create .env if needed
    echo "  cp .env.example .env"
    echo "  # Edit .env with your credentials"
}

# =============================================================================
# MAIN
# =============================================================================
case "$1" in
    systemd)
        create_systemd_service
        ;;
    cron)
        create_cron_job
        ;;
    screen)
        start_screen_session
        ;;
    setup)
        setup_server
        ;;
    *)
        echo "Polymarket Tail Bot - Server Deployment"
        echo ""
        echo "Usage: $0 {systemd|cron|screen|setup}"
        echo ""
        echo "  systemd - Create systemd service (recommended)"
        echo "  cron    - Show cron job configuration"
        echo "  screen  - Start in screen session"
        echo "  setup   - Show server setup instructions"
        ;;
esac
