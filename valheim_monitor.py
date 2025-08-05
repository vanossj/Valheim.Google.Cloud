#!/usr/bin/env python3

import re
import subprocess
import time
import logging
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Define the State Enum
class State(Enum):
    INITIALIZING = "initializing"
    LOBBY_STARTED = "lobby started"
    PLAYER_COUNT = "player count"

PLAYER_JOIN_RE = re.compile(r"Player joined server .* now (\d+) player\(s\)")
PLAYER_LEAVE_RE = re.compile(r"Player connection lost server .* now (\d+) player\(s\)")
LOBBY_STARTED_RE = re.compile(r"Session .* is active with 0 player\(s\)")
VALHEIM_SERVICE_NAME = "valheim.service"
GRACE_PERIOD = 15 * 60  # 15 minutes in seconds

shutdown_time = None
state = State.INITIALIZING  # Use the Enum for state
player_count = None


def shutdown_vm():
    """Shuts down the virtual machine."""
    logging.info("Virtual machine is shutting down due to inactivity.")
    subprocess.run(["sudo", "shutdown", "-h", "now"])


def determine_initial_state():
    global state, player_count

    process = subprocess.Popen(
        ["journalctl", "-u", VALHEIM_SERVICE_NAME, "-n", "1000", "-r"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in process.stdout:
        if PLAYER_JOIN_RE.search(line):
            player_count = int(PLAYER_JOIN_RE.search(line).group(1))
            state = State.PLAYER_COUNT
            logging.info(f"Initial state determined: '{state.value}' {player_count}")
            return
        elif PLAYER_LEAVE_RE.search(line):
            player_count = int(PLAYER_LEAVE_RE.search(line).group(1))
            state = State.PLAYER_COUNT
            logging.info(f"Initial state determined: '{state.value}' {player_count}")
            return
        elif LOBBY_STARTED_RE.search(line):
            state = State.LOBBY_STARTED
            logging.info(f"Initial state determined: '{state.value}'")
            return

    logging.info("No relevant logs found. Defaulting to 'initializing' state.")


def handle_log_line(line):
    global shutdown_time, state, player_count

    if state == State.INITIALIZING and LOBBY_STARTED_RE.search(line):
        state = State.LOBBY_STARTED
        logging.info(f"State changed to: {state.value}")

    join_match = PLAYER_JOIN_RE.search(line)
    if join_match:
        player_count = int(join_match.group(1))
        state = State.PLAYER_COUNT
        logging.info(f"State changed to: {state.value} {player_count}")
        shutdown_time = None  # Reset shutdown timer
        return

    leave_match = PLAYER_LEAVE_RE.search(line)
    if leave_match:
        player_count = int(leave_match.group(1))
        if player_count == 0:
            if shutdown_time is None:  # Start shutdown timer if not already set
                shutdown_time = time.time() + GRACE_PERIOD
                logging.info("No players online. Shutdown timer started.")
        else:
            state = State.PLAYER_COUNT
            logging.info(f"State changed to: {state.value} {player_count}")
            shutdown_time = None  # Reset shutdown timer

    logging.debug(f"Current state: {state.value}")


def follow_logs():
    process = subprocess.Popen(
        ["journalctl", "-u", VALHEIM_SERVICE_NAME, "-f", "-n", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        while True:
            line = process.stdout.readline()
            if line:
                handle_log_line(line)
            if shutdown_time and time.time() >= shutdown_time:
                shutdown_vm()
                break
    except KeyboardInterrupt:
        logging.info("Monitoring stopped.")
    finally:
        process.terminate()


if __name__ == "__main__":
    determine_initial_state()
    follow_logs()