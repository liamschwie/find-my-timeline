# src/find_my_timeline/cli.py
"""Command-line interface for AirTag Timeline."""

import logging
import os
import sys
import webbrowser
from pathlib import Path
from threading import Thread

import click
from dotenv import load_dotenv

from .auth import AuthenticationError, login, load_session
from .database import LocationDatabase
from .keys import KEYS_DIR, OWNED_BEACONS_DIR, export_keys, load_keys
from .poller import AccessoryPoller
from .web import create_app

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_config() -> dict:
    """Get configuration from environment variables."""
    default_db = str(Path.home() / ".find-my-timeline" / "locations.db")
    return {
        "min_interval": int(os.getenv("POLL_MIN_INTERVAL", "7")),
        "max_interval": int(os.getenv("POLL_MAX_INTERVAL", "10")),
        "db_path": os.getenv("DATABASE_PATH", default_db),
        "web_host": os.getenv("WEB_HOST", "127.0.0.1"),
        "web_port": int(os.getenv("WEB_PORT", "5000")),
    }


@click.group()
@click.version_option(version="0.1.0")
def main():
    """AirTag Timeline - track AirTag location and battery history."""


@main.command("import-keys")
def import_keys_cmd():
    """Export AirTag private keys from this Mac's local Find My cache (one-time)."""
    if not OWNED_BEACONS_DIR.exists():
        click.echo(f"No Find My accessory data found at {OWNED_BEACONS_DIR}", err=True)
        click.echo("Make sure Find My is set up on this Mac with at least one AirTag.", err=True)
        sys.exit(1)

    written = export_keys(source_dir=OWNED_BEACONS_DIR, dest_dir=KEYS_DIR)
    if not written:
        click.echo("No AirTags found to export.")
        return

    click.echo(f"Exported {len(written)} accessory key(s) to {KEYS_DIR}:")
    for path in written:
        click.echo(f"  - {path.stem}")


@main.command()
@click.option("--username", "-u", help="Apple ID email address")
@click.option("--password", "-p", help="Apple ID password", hide_input=True)
def auth(username, password):
    """Authenticate with Apple and store the session."""
    username = username or os.getenv("ICLOUD_USERNAME") or click.prompt("Enter your Apple ID")
    password = password or os.getenv("ICLOUD_PASSWORD") or click.prompt(
        "Enter your password", hide_input=True
    )

    click.echo(f"Authenticating as {username}...")
    try:
        login(username, password)
        click.echo("Authentication successful! Session saved.")
    except AuthenticationError as e:
        click.echo(f"Authentication failed: {e}", err=True)
        sys.exit(1)


def _build_poller(config: dict) -> AccessoryPoller:
    """Load the saved session and accessory keys, and build a poller. Exits on failure."""
    try:
        account = load_session()
    except AuthenticationError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    accessories = load_keys()
    if not accessories:
        click.echo(
            f"No accessory keys found in {KEYS_DIR}. Run 'find-my-timeline import-keys' first.",
            err=True,
        )
        sys.exit(1)

    database = LocationDatabase(config["db_path"])
    return AccessoryPoller(
        account=account,
        accessories=accessories,
        database=database,
        min_interval=config["min_interval"],
        max_interval=config["max_interval"],
    )


@main.command()
def poll():
    """Start the location polling service."""
    config = get_config()
    poller = _build_poller(config)

    click.echo(f"Starting poller (interval: {config['min_interval']}-{config['max_interval']} minutes)")
    click.echo(f"Database: {config['db_path']}")

    poller.on_poll(lambda locs: click.echo(f"Recorded {len(locs)} location(s)") if locs else None)

    try:
        poller.start()
    except KeyboardInterrupt:
        click.echo("\nStopping poller...")


@main.command()
@click.option("--host", "-h", help="Host to bind to")
@click.option("--port", "-p", type=int, help="Port to bind to")
@click.option("--open/--no-open", "open_browser", default=True, help="Open the map in your browser")
def web(host, port, open_browser):
    """Start the web interface."""
    config = get_config()
    host = host or config["web_host"]
    port = port or config["web_port"]

    database = LocationDatabase(config["db_path"])
    app = create_app(database)

    url = f"http://{host}:{port}"
    click.echo(f"Starting web server at {url}")
    if open_browser:
        webbrowser.open(url)
    app.run(host=host, port=port, debug=False)


@main.command()
@click.option("--host", help="Web server host")
@click.option("--port", type=int, help="Web server port")
@click.option("--open/--no-open", "open_browser", default=True, help="Open the map in your browser")
def start(host, port, open_browser):
    """Start both the poller and the web interface."""
    config = get_config()
    host = host or config["web_host"]
    port = port or config["web_port"]

    poller = _build_poller(config)
    app = create_app(poller.database)

    url = f"http://{host}:{port}"
    click.echo("Starting AirTag Timeline")
    click.echo(f"  Polling interval: {config['min_interval']}-{config['max_interval']} minutes")
    click.echo(f"  Web interface: {url}")
    click.echo(f"  Database: {config['db_path']}")

    poller_thread = Thread(target=poller.start, kwargs={"setup_signals": False}, daemon=True)
    poller_thread.start()

    if open_browser:
        webbrowser.open(url)

    try:
        app.run(host=host, port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
        poller.stop()


@main.command()
def stats():
    """Show database statistics."""
    config = get_config()
    db_path = Path(config["db_path"])

    if not db_path.exists():
        click.echo("No database found. Run 'poll' or 'start' first to begin collecting data.")
        return

    database = LocationDatabase(db_path)
    devices = database.get_devices()
    total = database.get_location_count()

    click.echo(f"Database: {db_path}")
    click.echo(f"Total locations: {total:,}")
    click.echo(f"Devices: {len(devices)}")

    for device in devices:
        count = database.get_location_count(device["id"])
        latest = database.get_latest_location(device["id"])
        latest_time = latest["timestamp"] if latest else "Never"

        click.echo(f"\n  {device['name']}")
        click.echo(f"    Locations: {count:,}")
        click.echo(f"    Last seen: {latest_time}")


@main.command()
def devices():
    """List all tracked AirTags."""
    config = get_config()
    db_path = Path(config["db_path"])

    if not db_path.exists():
        click.echo("No database found. Run 'poll' or 'start' first to begin collecting data.")
        return

    database = LocationDatabase(db_path)
    device_list = database.get_devices()

    if not device_list:
        click.echo("No devices found.")
        return

    click.echo(f"Tracked devices ({len(device_list)}):\n")
    for device in device_list:
        latest = database.get_latest_location(device["id"])
        click.echo(f"  {device['name']}")
        click.echo(f"    ID: {device['id']}")
        if latest:
            click.echo(f"    Last location: ({latest['latitude']:.6f}, {latest['longitude']:.6f})")
            click.echo(f"    Battery: {latest.get('battery_status') or 'Unknown'}")
            click.echo(f"    Last seen: {latest['timestamp']}")
        click.echo()


if __name__ == "__main__":
    main()
