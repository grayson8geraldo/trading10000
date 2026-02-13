"""
TradingView Webhook Handler.

Receives alerts from TradingView and converts them to trading signals.
This allows you to create custom alerts on TradingView charts and
have the bot execute trades automatically.

Setup:
1. Run the webhook server (or use ngrok to expose it)
2. In TradingView, create an alert with webhook URL: http://YOUR_IP:5000/webhook
3. Set alert message format (see ALERT_FORMAT below)
"""

import json
import hmac
import hashlib
from flask import Flask, request, jsonify
from utils.logger import log
from config.settings import WEBHOOK_HOST, WEBHOOK_PORT, WEBHOOK_SECRET

app = Flask(__name__)

# Callback function set by the main bot
_signal_callback = None

# ============================================================
# ALERT FORMAT for TradingView alerts:
# ============================================================
# {
#   "secret": "your_webhook_secret",
#   "symbol": "BTCUSDT",
#   "side": "buy",
#   "action": "open",
#   "price": {{close}},
#   "strategy": "manual",
#   "stop_loss": 0,
#   "take_profit": 0,
#   "message": "EMA crossover bullish"
# }
#
# TradingView variables you can use:
# {{ticker}} - Symbol
# {{close}} - Current close price
# {{open}}, {{high}}, {{low}} - OHLC
# {{volume}} - Volume
# {{time}} - Timestamp
# ============================================================

ALERT_FORMAT_EXAMPLE = """{
  "secret": "your_webhook_secret",
  "symbol": "BTCUSDT",
  "side": "buy",
  "action": "open",
  "price": {{close}},
  "strategy": "tv_alert",
  "stop_loss": 0,
  "take_profit": 0,
  "message": "Custom signal description"
}"""


def set_signal_callback(callback):
    """Set the callback function for processing signals."""
    global _signal_callback
    _signal_callback = callback


def verify_secret(data: dict) -> bool:
    """Verify the webhook secret."""
    return data.get("secret") == WEBHOOK_SECRET


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming TradingView webhook alerts."""
    try:
        # Parse JSON payload
        if request.is_json:
            data = request.get_json()
        else:
            # Try to parse as text (TradingView sometimes sends plain text)
            try:
                data = json.loads(request.data.decode("utf-8"))
            except json.JSONDecodeError:
                log.warning("Invalid webhook payload (not JSON)")
                return jsonify({"error": "Invalid JSON"}), 400

        log.info(f"Webhook received: {data}")

        # Verify secret
        if not verify_secret(data):
            log.warning("Invalid webhook secret")
            return jsonify({"error": "Unauthorized"}), 401

        # Validate required fields
        required = ["symbol", "side", "action"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        # Normalize symbol format
        symbol = data["symbol"].upper()
        if "/" not in symbol:
            # Convert BTCUSDT -> BTC/USDT
            for quote in ["USDT", "BUSD", "USDC"]:
                if symbol.endswith(quote):
                    base = symbol[:-len(quote)]
                    symbol = f"{base}/{quote}"
                    break

        # Build signal data
        signal_data = {
            "symbol": symbol,
            "side": data["side"].lower(),
            "action": data["action"].lower(),  # open, close, reverse
            "price": float(data.get("price", 0)),
            "strategy": data.get("strategy", "tv_manual"),
            "stop_loss": float(data.get("stop_loss", 0)),
            "take_profit": float(data.get("take_profit", 0)),
            "message": data.get("message", ""),
        }

        # Process signal
        if _signal_callback:
            result = _signal_callback(signal_data)
            return jsonify({"status": "ok", "result": result}), 200
        else:
            log.warning("No signal callback registered")
            return jsonify({"status": "ok", "note": "No handler registered"}), 200

    except Exception as e:
        log.error(f"Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "alive"}), 200


@app.route("/alert-format", methods=["GET"])
def alert_format():
    """Return the expected alert format for TradingView."""
    return jsonify({
        "format": ALERT_FORMAT_EXAMPLE,
        "description": "Use this JSON format in your TradingView alert webhook message",
    }), 200


def start_webhook_server():
    """Start the webhook server."""
    log.info(f"Starting webhook server on {WEBHOOK_HOST}:{WEBHOOK_PORT}")
    app.run(host=WEBHOOK_HOST, port=WEBHOOK_PORT, debug=False)
