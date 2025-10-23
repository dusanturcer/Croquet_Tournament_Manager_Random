import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
from datetime import datetime
from collections import Counter

# --- Player and Match Classes ---

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.points = 0  
        self.wins = 0  
        self.hoops_scored = 0  
        self.hoops_conceded = 0 
        self.opponents = set()

    def add_opponent(self, opponent_id):
        self.opponents.add(opponent_id)

class Match:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.result = None  # (hoops1, hoops2)

    def set_result(self, hoops1, hoops2):
        hoops1, hoops2 = int(hoops1), int(hoops2)
        
        if self.player2 is None:
            self.result = (hoops1, hoops2)
            return
            
        self.player1.hoops_scored += hoops1
        self.player1.hoops_conceded += hoops2
        self.player2.hoops_scored += hoops2
        self.player2.hoops_conceded += hoops1

        if hoops1 > hoops2:
            self.player1.wins += 1
            self.player1.points += 1
        elif hoops2 > hoops1:
            self.player2.wins += 1
            self.player2.points += 1
        
        self.result = (hoops1, hoops2)

    def get_scores(self):
        # Data is counted as (0, 0) if no result is set (i.e., match hasn't been played yet)
        return self.result if self.result else (0, 0)

class SwissTournament:
    def __init__(self, players_names_or_objects, num_rounds):
        if all(isinstance(p, str) for p in players_names_or_objects):
            self.players = [Player(i, name) for i, name in enumerate(players_names_or_objects)]
            self.rounds = []
            for round_num in range(num_rounds):
                # Only generate pairings for Round 0 during init
                if round_num == 0:
                   self.generate_round_pairings(round_num, initial=True) 
                else:
                    # Initialize empty round lists for subsequent rounds
                    self.rounds.append([])
        else:
            self.players = players_names_or_objects
            self.rounds = [] 
            
        self.num_rounds = num_rounds
        
    def generate_round_pairings(self, round_num, initial=False):
        while len(self.rounds) <= round_num:
            self.rounds.append([])
        
        self.rounds[round_num] = [] 
        round_pairings = []
        
        if initial:
            # First round: random pairings
            available_players = self.players.copy()
            random.shuffle(available_players) 
        else:
            # Subsequent rounds: sort by standings
            available_players = self.get_standings()
        
        used_players = set()
        
        # Reset opponents set for the purpose of THIS pairing algorithm iteration
        # This is a key step in Swiss system pairing
        temp_players = available_players.copy()
        
        for i in range(len(temp_players)):
            p1 = temp_players[i]
            if p1.id in used_players:
                continue
            
            best_p2 = None
            
            # Look for the highest-ranked available opponent p2 that p1 hasn't played
            for j in range(i + 1, len(temp_players)):
                p2 = temp_players[j]
                if p2.id not in used_players and p2.id not in p1.opponents:
                    best_p2 = p2
                    break
            
            # Fallback: if no available opponent hasn't been played, find any available
            if not best_p2:
                 for j in range(i + 1, len(temp_players)):
                    p2 = temp_players[j]
                    if p2.id not in used_players:
                        best_p2 = p2
                        # st.warning(f"Forced re-match between {p1.name} and {p2.name} in round {round_num + 1}")
                        break
            
            if best_p2:
                round_pairings.append(Match(p1, best_p2))
                used_players.add(p1.id)
                used_players.add(best_p2.id)
                p1.add_opponent(best_p2.id)
                best_p2.add_opponent(p1.id)
            
        remaining_players = [p for p in temp_players if p.id not in used_players]
        if remaining_players:
            # Player with the lowest score who hasn't had a bye gets the bye
            bye_player = remaining_players[0]
            if len(remaining_players) > 1:
                # Find the player with the fewest past byes (simple check for now)
                
                # Check for existing bye matches (simplistic way)
                bye_counts = Counter()
                for r in self.rounds:
                    for match in r:
                        if match and match.player2 is None:
                            bye_counts[match.player1.id] += 1
                            
                # Sort remaining players to find the one with the fewest byes
                remaining_players.sort(key=lambda p: (bye_counts[p.id], p.points)) 
                bye_player = remaining_players[0]
                
            round_pairings.append(Match(bye_player, None))
            used_players.add(bye_player.id)
        
        self.rounds[round_num] = round_pairings
        
        # if len(used_players) != len(self.players):
        #      st.warning(f"Warning: Only {len(used_players)}/{len(self.players)} players paired in round {round_num + 1}.")

    def record_result(self, round_num, match_num, hoops1, hoops2):
        if 0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num]):
            match = self.rounds[round_num][match_num]
            
            p1, p2 = match.player1, match.player2
            old_hoops1, old_hoops2 = match.get_scores()
            
            # Reset previous results
            if match.result is not None:
                if p2 is not None:
                    p1.hoops_scored -= old_hoops1
                    p1.hoops_conceded -= old_hoops2
                    p2.hoops_scored -= old_hoops2
                    p2.hoops_conceded -= old_hoops1
                    
                    if old_hoops1 > old_hoops2:
                        p1.wins -= 1
                        p1.points -= 1
                    elif old_hoops2 > old_hoops1:
                        p2.wins -= 1
                        p2.points -= 1
            
            match.set_result(hoops1, hoops2)

    def get_standings(self):
        return sorted(self.players, key=lambda p: (p.points, p.hoops_scored - p.hoops_conceded, p.hoops_scored), reverse=True)

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []

# ----------------------------------------------------------------------
# --- Database Functions ---
# ----------------------------------------------------------------------

DB_PATH = 'tournament.db'

def get_db_mtime(db_path=DB_PATH):
    """Gets the last modification time of the database file."""
    if os.path.exists(db_path):
        return os.path.getmtime(db_path)
    return 0.0

def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
                
    c.execute('''CREATE TABLE IF NOT EXISTS players
                (tournament_id INTEGER, player_id INTEGER, name TEXT, 
                 points INTEGER, wins INTEGER, 
                 hoops_scored INTEGER, hoops_conceded INTEGER,
                 PRIMARY KEY (tournament_id, player_id),
                 FOREIGN KEY (tournament_id) REFERENCES tournaments(id))''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS matches
                (tournament_id INTEGER, round_num INTEGER, match_num INTEGER,
                 player1_id INTEGER, player2_id INTEGER, hoops1 INTEGER, hoops2 INTEGER)''')
    conn.commit()
    return conn

def save_to_db(tournament, tournament_name, conn):
    try:
        c = conn.cursor()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("SELECT id FROM tournaments WHERE name = ?", (tournament_name,))
        existing_id = c.fetchone()

        if existing_id:
            tournament_id = existing_id[0]
            c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament_id,))
            c.execute("DELETE FROM MATCHES WHERE tournament_id = ?", (tournament_id,))
            c.execute("UPDATE tournaments SET name = ?, date = ? WHERE id = ?", (tournament_name, date, tournament_id))
        else:
            c.execute("INSERT INTO tournaments (name, date) VALUES (?, ?)", (tournament_name, date))
            tournament_id = c.lastrowid

        player_data = [(tournament_id, p.id, p.name, p.points, p.wins, p.hoops_scored, p.hoops_conceded) for p in tournament.players]
        c.executemany("INSERT INTO players (tournament_id, player_id, name, points, wins, hoops_scored, hoops_conceded) VALUES (?, ?, ?, ?, ?, ?, ?)", player_data)

        match_data = []
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                if match is None: continue
                hoops1, hoops2 = match.get_scores()
                player2_id = match.player2.id if match.player2 else -1
                match_data.append((tournament_id, round_num, match_num, match.player1.id, player2_id, hoops1, hoops2))

        c.executemany("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, hoops1, hoops2) VALUES (?, ?, ?, ?, ?, ?, ?)", match_data)

        conn.commit()
        
        # Invalidate the cached list of tournaments on successful save
        st.cache_data.clear() 
        
        return tournament_id
        
    except sqlite3.Error as e:
        st.error(f"Database error on save: {e}")
        conn.rollback() 
        return None

def delete_tournament_from_db(tournament_id, db_path=DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament_id,))
        c.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament_id,))
        c.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
        
        conn.commit()
        conn.close()
        
        # Invalidate the cached list of tournaments on successful delete
        st.cache_data.clear()
        
        return True
    except sqlite3.Error as e:
        st.error(f"Database error on delete: {e}")
        return False

@st.cache_data(show_spinner="Refreshing tournament list...")
def load_tournaments_list(db_mtime, db_path=DB_PATH): 
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, name, date FROM tournaments ORDER BY date DESC")
    tournaments = c.fetchall()
    conn.close()
    
    name_counts = Counter(t[1] for t in tournaments)

    result_list = []
    
    for t_id, t_name, t_date in tournaments:
        display_name = t_name
        
        if name_counts[t_name] > 1:
            display_name = f"{t_name} ({t_date.split(' ')[0]})"
            
        result_list.append((t_id, display_name))
        
    return result_list

def load_tournament_data(tournament_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("SELECT name FROM tournaments WHERE id = ?", (tournament_id,))
    tournament_name = c.fetchone()[0]

    c.execute("SELECT player_id, name, points, wins, hoops_scored, hoops_conceded FROM players WHERE tournament_id = ? ORDER BY player_id", (tournament_id,))
    player_data = c.fetchall()
    
    player_map = {}
    for p_id, name, points, wins, hs, hc in player_data:
        player = Player(p_id, name)
        player.points = points
        player.wins = wins
        player.hoops_scored = hs
        player.hoops_conceded = hc
        player_map[p_id] = player
        
    players_list = list(player_map.values())

    num_rounds_query = c.execute("SELECT MAX(round_num) FROM matches WHERE tournament_id = ?", (tournament_id,)).fetchone()
    # num_rounds is the maximum scheduled rounds from the player setup, NOT the max round number in the matches table
    # We must retrieve the initial `num_rounds` from player setup or rely on session state after loading.
    # For simplicity during loading, we'll ensure the tournament object is created with at least 
    # the maximum round number + 1, and the correct `num_rounds` will be stored in session state.
    max_round_in_db = (num_rounds_query[0] + 1) if num_rounds_query[0] is not None else 1
    
    # Initialize tournament with max rounds seen in DB or default to 3
    tournament = SwissTournament(players_list, max(max_round_in_db, 3))
    # Explicitly set rounds list size based on loaded data
    tournament.rounds = [[] for _ in range(max_round_in_db)] 
    
    c.execute("SELECT round_num, match_num, player1_id, player2_id, hoops1, hoops2 FROM matches WHERE tournament_id = ? ORDER BY round_num, match_num", (tournament_id,))
    match_data = c.fetchall()

    for r_num, m_num, p1_id, p2_id, h1, h2 in match_data:
        p1 = player_map.get(p1_id)
        p2 = player_map.get(p2_id) if p2_id != -1 else None
        
        if p1 is None: continue

        # Restore opponents set, required for generating future rounds
        if p2 is not None:
            p1.add_opponent(p2_id)
            p2.add_opponent(p1_id)

        match = Match(p1, p2)
        match.result = (h1, h2)
        
        # Ensure the round list is large enough
        while len(tournament.rounds) <= r_num:
            tournament.rounds.append([])
            
        if len(tournament.rounds[r_num]) <= m_num:
             tournament.rounds[r_num].extend([None] * (m_num - len(tournament.rounds[r_num]) + 1))
        
        tournament.rounds[r_num][m_num] = match
        
        # Re-apply match result to correctly set points/hoops.
        # This is a cleaner way to restore state than relying only on the DB save columns.
        if p2 is not None:
             p1.hoops_scored += h1
             p1.hoops_conceded += h2
             p2.hoops_scored += h2
             p2.hoops_conceded += h1
             
             if h1 > h2:
                 p1.points += 1
                 p1.wins += 1
             elif h2 > h1:
                 p2.points += 1
                 p2.wins += 1

    conn.close()
    
    # The actual scheduled number of rounds is lost in the DB. We'll use the 
    # max round number found in the DB as the temporary scheduled number, 
    # or rely on the fact that if it was saved, the original `num_rounds` 
    # was likely in the session state already. For now, we return `max_round_in_db`.
    # When a loaded tournament is saved, the current session state `num_rounds`
    # will be used for the next session.
    return tournament, tournament_name, max_round_in_db

# --- Export Functions ---

def export_to_csv(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.csv"
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Round', 'Match', 'Player 1', 'Player 2', 'Hoops 1', 'Hoops 2'])
            for round_num, round_pairings in enumerate(tournament.rounds):
                for match_num, match in enumerate(round_pairings):
                    if match is None: continue
                    player2 = match.player2.name if match.player2 else 'BYE'
                    hoops1, hoops2 = match.get_scores()
                    writer.writerow([round_num + 1, match_num + 1, match.player1.name, player2, hoops1, hoops2])
        return filename
    except IOError as e:
        st.error(f"Error writing CSV: {e}")
        return None

def export_to_excel(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.xlsx"
        data = []
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                if match is None: continue
                player2 = match.player2.name if match.player2 else 'BYE'
                hoops1, hoops2 = match.get_scores()
                data.append({
                    'Round': round_num + 1,
                    'Match': match_num + 1,
                    'Player 1': match.player1.name,
                    'Player 2': player2,
                    'Hoops 1': hoops1,
                    'Hoops 2': hoops2
                })
        df = pd.DataFrame(data)
        df.to_excel(filename, index=False)
        return filename
    except Exception as e:
        st.error(f"Error writing Excel: {e}")
        return None


# ----------------------------------------------------------------------
# --- Streamlit UI and Logic (Main Function) ---
# ----------------------------------------------------------------------

def _update_session_state_to_int(text_key, result_key, min_value, max_value):
    """
    Callback function to convert the text input to a clean integer.
    It reads from text_key (string) and writes the cleaned integer to result_key (int).
    """
    raw_value = st.session_state[text_key]
    
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
    
    if not raw_value:
        st.session_state[result_key] = 0
    else:
        try:
            num = int(raw_value)
            
            # Apply bounds checking
            if num < min_value:
                st.session_state[result_key] = min_value
            elif num > max_value:
                st.session_state[result_key] = max_value
            else:
                st.session_state[result_key] = num
                
        except ValueError:
            # If the user enters non-numeric text, reset result to 0
            st.session_state[result_key] = 0
            
# Updated number_input_simple function
def number_input_simple(key, min_value=0, max_value=26, step=1, label="", disabled=False):
    
    text_key = f"{key}_text" 
    result_key = f"{key}_result" 

    # 1. Get current clean integer result. 
    current_value_int = st.session_state.get(result_key, 0)
    
    # 2. Determine the string to DISPLAY in the box. 
    if text_key not in st.session_state or st.session_state[text_key] == "":
        display_value = "" if current_value_int == 0 else str(current_value_int)
    else:
        # Check if the text input is still valid (allows temporary invalid input)
        try:
            test_int = int(st.session_state[text_key])
            if test_int == current_value_int:
                 display_value = st.session_state[text_key]
            else:
                display_value = str(current_value_int)
        except ValueError:
            display_value = st.session_state[text_key]

    # 3. Render the st.text_input using text_key for its string value.
    st.text_input(
        label,
        value=display_value,
        max_chars=2, 
        key=text_key, # This key stores the raw string input (must be a string)
        help="Enter score. Max 26.",
        disabled=disabled,
        on_change=lambda: _update_session_state_to_int(text_key, result_key, min_value, max_value)
    )
    
    # 4. Return the clean integer result.
    return int(st.session_state.get(result_key, 0))


def load_selected_tournament(selected_id):
    if selected_id:
        try:
            tournament, tournament_name, num_rounds_loaded = load_tournament_data(selected_id)
            
            # Clear all old match score states for the previous tournament
            for key in list(st.session_state.keys()):
                if key.startswith(("hoops1_", "hoops2_")):
                    del st.session_state[key]
            
            st.session_state.tournament = tournament
            st.session_state.tournament_name = tournament_name
            
            # Use the number of rounds defined in the state if it was already set, 
            # otherwise use the loaded value.
            if 'num_rounds' not in st.session_state or st.session_state.num_rounds < num_rounds_loaded:
                 st.session_state.num_rounds = num_rounds_loaded
                 tournament.num_rounds = num_rounds_loaded # Ensure the tournament object also reflects the loaded count
                 
            st.session_state.players = [p.name for p in tournament.players]
            st.session_state.loaded_id = selected_id # Store the ID of the currently loaded tournament
            st.success(f"Tournament '{tournament_name}' loaded successfully.")
            
        except Exception as e:
            st.error(f"Error loading tournament data: {e}")
            st.session_state.tournament = None
            st.session_state.loaded_id = None

# Callback function to set the flag and trigger the main script's rerun
def handle_lock_change():
    """Sets a flag to force a full rerun from the main script body."""
    st.session_state._lock_changed = True


def main():
    st.set_page_config(layout="wide", page_title="Croquet Tournament Manager")
    
    # --- Custom CSS (For aesthetics and the green text) ---
    st.markdown("""
        <style>
        /* Green Button Styles (General Buttons) */
        div.stButton > button, 
        .stButton button {
            background-color: #4CAF50 !important; 
            color: white !important; 
            border: 1px solid #388E3C !important; 
            border-radius: 5px !important;
            padding: 10px 24px !important;
            transition: 0.3s;
            width: 100% !important; 
        }
        
        /* Hover effect (slightly darker green) on all button types */
        div.stButton > button:hover,
        .stButton button:hover,
        button[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
            background-color: #388E3C !important;
            border: 1px solid #2E7D32 !important;
        }

        /* --- SPECIFICALLY TARGET THE FORM SUBMIT BUTTON (GREEN) --- */
        button[data-testid="stBaseButton-secondaryFormSubmit"] {
            background-color: #4CAF50 !important;
            color: white !important;
            border: 1px solid #388E3C !important;
        }
        
        /* Make the text input area bold */
        /* Targets the container around st.text_input */
        div[data-testid^="stTextInput"] input {
            color: black !important; 
            font-weight: bold;
            text-align: center; /* Center the score for better alignment */
        }
        
        /* Ensure the form container doesn't reset button width */
        .stForm div[data-testid="stFormSubmitButton"] {
            width: 100%;
        }
        
        /* CSS for the success text (the requested green font) */
        .round-complete-text {
            color: #4CAF50; /* Green color */
            font-weight: bold;
            margin-top: -10px; /* Pull it up closer to the expander */
            padding-left: 10px;
        }

        </style>
        """, unsafe_allow_html=True)
    # --- End Custom CSS ---
    
    st.title("Croquet Tournament Manager 🏏 (Swiss System, No Draws)")

    # Initialize ALL state variables at the start 
    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3
        st.session_state.loaded_id = None 
    
    # Initialize the new lock state and the rerun flag
    if 'is_locked' not in st.session_state:
        st.session_state.is_locked = "Unlocked"
    if '_lock_changed' not in st.session_state:
        st.session_state._lock_changed = False
        
    # Convert radio button selection to boolean for logic
    is_locked_bool = (st.session_state.is_locked == "Locked")
        
    # Check the flag and show toast here in the main script body
    if st.session_state._lock_changed:
        st.session_state._lock_changed = False  # Reset flag
        
        if is_locked_bool:
            st.toast("🔒 Tournament Input is Locked", icon="🚫")
        else:
            st.toast("🔓 Tournament Input is Unlocked", icon="✅")
            
        st.rerun()  # Force the full rerun to apply the disabled state

    # --- Sidebar for Loading Saved Tournaments and LOCK BUTTON ---
    with st.sidebar:
        st.header("App Status")
        
        # Radio Button for Locking the app (Triggers handle_lock_change callback)
        st.session_state.is_locked = st.radio(
            "Tournament Input Status",
            ["Unlocked", "Locked"],
            key="lock_radio",
            horizontal=True,
            help="**Locked** prevents entry of scores and submission of results on this device.",
            on_change=handle_lock_change
        )
        
        st.header("Load Saved Tournament")
        init_db()
        
        # Pass the database modification time to cache the list effectively
        db_mtime = get_db_mtime()
        tournaments_list = load_tournaments_list(db_mtime)
        
        display_list = ["--- New Tournament ---"] + [t[1] for t in tournaments_list]
        id_map = {t[1]: t[0] for t in tournaments_list}
        
        # Determine the correct default index for the selectbox
        default_index = 0
        current_loaded_id = st.session_state.loaded_id 
        
        if current_loaded_id is not None:
            for idx, (t_id, display_name) in enumerate(tournaments_list):
                if t_id == current_loaded_id:
                    default_index = idx + 1
                    break
        
        selected_display = st.selectbox(
            "Select a tournament to load:",
            display_list,
            index=default_index,
            key="load_selectbox"
        )
        
        selected_id = id_map.get(selected_display)
        
        # --- Logic for handling the selection ---
        
        # Action: Start New Tournament
        if selected_display == "--- New Tournament ---":
            if st.session_state.tournament and st.session_state.loaded_id is not None:
                if st.button("Start New Tournament", key="new_tournament_button"):
                    st.session_state.tournament = None
                    st.session_state.tournament_name = "New Tournament"
                    st.session_state.players = []
                    st.session_state.num_rounds = 3
                    st.session_state.loaded_id = None
                    st.rerun()
        
        # Action: Load/Re-load Selected Tournament
        elif selected_id and selected_id != st.session_state.loaded_id:
            load_selected_tournament(selected_id)
            st.rerun()

        # Action: Delete Tournament
        if selected_id:
            st.markdown("---")
            st.warning("PERMANENT ACTION")
            if st.button(f"🗑️ Delete Tournament", key="delete_button", disabled=is_locked_bool):
                if delete_tournament_from_db(selected_id):
                    st.success(f"Tournament '{selected_display}' deleted. Reloading page...")
                    st.session_state.tournament = None
                    st.session_state.tournament_name = "New Tournament"
                    st.session_state.loaded_id = None
                    st.rerun()
                else:
                    st.error("Failed to delete the tournament.")

    # --- Main Content: Tournament Setup (Disabled if Locked) ---
    if not st.session_state.tournament or not st.session_state.players:
        expander_state = True
    else:
        expander_state = False
        
    with st.expander("Create/Setup Tournament", expanded=expander_state):
        with st.form("tournament_form_setup"):
            # DISABLE SETUP INPUTS IF LOCKED
            st.session_state.tournament_name = st.text_input("Tournament Name", value=st.session_state.tournament_name, disabled=is_locked_bool)
            player_input = st.text_area("Enter player names (one per line)", "\n".join(st.session_state.players), disabled=is_locked_bool)
            st.session_state.num_rounds = st.number_input("Number of Rounds", min_value=1, max_value=10, value=st.session_state.num_rounds, step=1, disabled=is_locked_bool)
            submitted = st.form_submit_button("Create Tournament", disabled=is_locked_bool)

            if submitted and st.session_state.tournament_name and player_input:
                st.session_state.players = [name.strip() for name in player_input.split('\n') if name.strip()]
                if len(st.session_state.players) < 2:
                    st.error("At least 2 players are required!")
                else:
                    # Clear old score states from any previous tournament
                    for key in list(st.session_state.keys()):
                        if key.startswith(("hoops1_", "hoops2_")):
                            if key in st.session_state:
                                del st.session_state[key]
                            
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.session_state.loaded_id = None # Mark as a new, unsaved tournament
                    st.success(f"Tournament '{st.session_state.tournament_name}' created! Pairings for Round 1 generated. Scroll down to enter results.")
                    st.rerun() # Rerun to update the page structure

    # --- Main Content: Tournament Management ---
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        st.header(f"Active Tournament: {st.session_state.tournament_name}")

        # --- Match Results & Pairing Display ---
        st.subheader("Match Results & Input")
        
        score_keys_to_update = [] 
        
        # Pre-process all keys and initialize session state before the form runs
        for round_num in range(len(tournament.rounds)): # Iterate over generated rounds only
            pairings = tournament.get_round_pairings(round_num)
            for match_num, match in enumerate(pairings):
                if match and match.player2 is not None:
                    hoops1_key_root = f"hoops1_r{round_num}_m{match_num}"
                    hoops2_key_root = f"hoops2_r{round_num}_m{match_num}"
                    
                    result1_key = f"{hoops1_key_root}_result"
                    result2_key = f"{hoops2_key_root}_result"
                    
                    current_hoops1, current_hoops2 = match.get_scores()
                    
                    # Initialize Streamlit session state with current DB values (as integers)
                    if result1_key not in st.session_state:
                        st.session_state[result1_key] = current_hoops1
                    
                    if result2_key not in st.session_state:
                        st.session_state[result2_key] = current_hoops2
                        
                    score_keys_to_update.append((round_num, match_num, hoops1_key_root, hoops2_key_root))

        # RENDER INPUTS (OUTSIDE THE FORM)
        for round_num in range(len(tournament.rounds)):
            round_pairings = tournament.get_round_pairings(round_num)
            
            non_bye_matches = [match for match in round_pairings if match and match.player2 is not None]
            
            if not non_bye_matches:
                if round_num == 0 and len(tournament.players) > 0 and len(tournament.rounds) > 0 and len(tournament.rounds[0]) == 0:
                     st.warning("No pairings were generated for Round 1. Please check player count or restart.")
                continue
            
            # Completion check based on non-bye matches having a score entered
            is_round_complete = all(sum(m.get_scores()) > 0 for m in non_bye_matches)

            round_label = f"Round {round_num + 1} ({len(non_bye_matches)} matches)"
            
            # Expanded logic: expand the latest, incomplete round
            expanded_state = not is_round_complete and (round_num == len(tournament.rounds) - 1)

            with st.expander(round_label, expanded=expanded_state):
                
                match_col1, match_col2 = st.columns(2)
                match_display_num = 1
                
                for i, match in enumerate(round_pairings):
                    if match is None or match.player2 is None:
                        continue 
                        
                    current_match_col = match_col1 if match_display_num % 2 != 0 else match_col2
                    
                    # Find the corresponding keys in score_keys_to_update
                    match_info = next(((r, m, k1, k2) 
                                       for r, m, k1, k2 in score_keys_to_update 
                                       if r == round_num and m == round_pairings.index(match)), None)
                    
                    if match_info is None:
                        # Should not happen if pre-processing was correct
                        continue

                    hoops1_key_root = match_info[2]
                    hoops2_key_root = match_info[3]
                    
                    with current_match_col:
                        
                        col_num, col_p1, col_h1, col_h2, col_p2, col_status = st.columns([0.5, 2, 1, 1, 2, 1.5])
                        
                        with col_num:
                            st.markdown(f"**{match_display_num}:**")
                            
                        with col_p1:
                            st.markdown(f"**<h4 style='text-align: left;'>{match.player1.name}</h4>**", unsafe_allow_html=True)
                            
                        with col_h1:
                            live_hoops1 = number_input_simple(key=hoops1_key_root, disabled=is_locked_bool)
                        
                        with col_h2:
                            live_hoops2 = number_input_simple(key=hoops2_key_root, disabled=is_locked_bool)
                        
                        with col_p2:
                            st.markdown(f"**<h4 style='text-align: left;'>{match.player2.name}</h4>**", unsafe_allow_html=True)
                            
                        with col_status:
                            
                            if live_hoops1 == 0 and live_hoops2 == 0:
                                status_text = " - " 
                                status_delta = " "
                            else:
                                status_text = f"{live_hoops1} - {live_hoops2}"
                                
                                if live_hoops1 > live_hoops2:
                                    status_delta = "P1 Wins"
                                elif live_hoops2 > live_hoops1:
                                    status_delta = "P2 Wins"
                                else: 
                                    status_delta = "Draw (0 pts)"

                            st.metric(label="Score", value=status_text, delta=status_delta)
                                
                        current_match_col.markdown("---")
                        match_display_num += 1
                        
                # Display BYE player if any
                bye_match = next((match for match in round_pairings if match and match.player2 is None), None)
                if bye_match:
                    st.info(f"**BYE Player:** {bye_match.player1.name} (Awarded 1 point and 26-0 score for tie-breaking)")


        # --- Update Results Form ---
        is_form_disabled = is_locked_bool

        with st.form("update_results_form"):
            st.markdown("### Apply & Save Results")
            st.info("Click 'Update Standings & Save to DB' to apply all entered scores above and save the entire tournament state.")
            
            submitted = st.form_submit_button("💾 Update Standings & Save to DB", disabled=is_form_disabled)
            
            if submitted and not is_form_disabled:
                # 1. Update the tournament object with scores from session state
                match_updates_made = False
                
                # Reset all points/hoops before applying new results
                for p in tournament.players:
                    p.points = p.wins = p.hoops_scored = p.hoops_conceded = 0
                
                # Re-apply all match results to ensure points are correct
                for r_num, round_pairings in enumerate(tournament.rounds):
                    for m_num, match in enumerate(round_pairings):
                        if match is None: continue
                        
                        hoops1, hoops2 = match.get_scores() # Current score in the match object
                        
                        # Check session state for updated score only if it was a non-bye match
                        if match.player2 is not None:
                            try:
                                # Find the keys used for this match
                                match_info = next(((r, m, k1, k2) for r, m, k1, k2 in score_keys_to_update if r == r_num and m == m_num))
                                k1_root, k2_root = match_info[2], match_info[3]
                                
                                live_hoops1 = st.session_state.get(f"{k1_root}_result", 0)
                                live_hoops2 = st.session_state.get(f"{k2_root}_result", 0)
                                
                                # If the session state has a newer score, use it and mark for saving
                                if (live_hoops1, live_hoops2) != (hoops1, hoops2):
                                    hoops1, hoops2 = live_hoops1, live_hoops2
                                    match_updates_made = True
                                
                            except StopIteration:
                                pass # This match was likely generated but not in the score_keys_to_update list (i.e. if a round was just generated)
                        
                        # Apply scores. This handles points, wins, and hoop stats.
                        # Note: This is an internal call to Match.set_result which does NOT update opponents.
                        # We use a temporary match to apply scores without changing opponent history
                        temp_match = Match(match.player1, match.player2) 
                        temp_match.set_result(hoops1, hoops2) 
                        match.result = temp_match.result
                        
                        # Apply BYE rule: 1 point, 26-0 hoop differential for tie-breaker
                        if match.player2 is None and hoops1 == 0 and hoops2 == 0:
                            match.player1.points += 1 # 1 point for the BYE
                            match.player1.hoops_scored += 26
                            match_updates_made = True


                # 2. Save the updated tournament to the database
                conn = init_db()
                tournament_id = save_to_db(tournament, st.session_state.tournament_name, conn)
                conn.close()
                
                if tournament_id:
                    st.session_state.loaded_id = tournament_id
                    st.success("Results updated and tournament saved successfully!")
                    
                    # If matches were updated, rerun to refresh standings and inputs
                    if match_updates_made:
                        st.rerun()

        st.markdown("---")
        
        # --- Standings Display ---
        st.subheader("Current Standings 🏆")
        standings = tournament.get_standings()
        
        data = []
        for i, p in enumerate(standings):
            data.append({
                'Rank': i + 1,
                'Player': p.name,
                'Points': p.points,
                'Wins': p.wins,
                'Hoops For': p.hoops_scored,
                'Hoops Against': p.hoops_conceded,
                'Hoop Diff': p.hoops_scored - p.hoops_conceded
            })
        
        standings_df = pd.DataFrame(data)
        
        # Style the DataFrame to highlight the top three
        def highlight_top3(s):
            is_top3 = s.index < 3
            return ['background-color: #ffd70030' if v else '' for v in is_top3] # Light Gold background
        
        st.dataframe(
            standings_df.style.apply(highlight_top3, subset=['Rank', 'Player', 'Points', 'Wins', 'Hoop Diff']),
            hide_index=True,
            use_container_width=True
        )

        st.markdown("---")

        # --- Next Round Logic (Corrected) ---
        current_generated_rounds = len(tournament.rounds)
        total_scheduled_rounds = tournament.num_rounds
        
        # 1. Check if the LAST GENERATED round is complete
        last_generated_round_num = current_generated_rounds - 1 
        all_matches_completed = False
        
        if last_generated_round_num >= 0:
            last_round_pairings = tournament.get_round_pairings(last_generated_round_num)
            # Check only non-bye matches
            non_bye_matches = [match for match in last_round_pairings if match and match.player2 is not None]
            
            # A round is considered complete if ALL non-bye matches have non-zero scores
            all_matches_completed = all(sum(match.get_scores()) > 0 for match in non_bye_matches)
        else:
            # If current_generated_rounds is 0 (i.e., Round 1 hasn't been generated yet during setup), allow generation
            all_matches_completed = True 
        
        # --- FINAL TOURNAMENT COMPLETION CHECK ---
        if current_generated_rounds == total_scheduled_rounds and all_matches_completed:
            st.balloons() # Add celebratory balloons!
            st.success(f"✅ Tournament Complete! All {total_scheduled_rounds} scheduled rounds have been played.")
        
        # --- INTERMEDIATE ROUND GENERATION CHECK ---
        elif current_generated_rounds < total_scheduled_rounds:
            
            round_to_generate = current_generated_rounds + 1
            st.subheader(f"Next Round: Round {round_to_generate}")
            
            if all_matches_completed:
                if current_generated_rounds > 0:
                     # Message for completed intermediate round
                     st.success(f"Round {current_generated_rounds} results are complete! Ready to generate pairings for Round {round_to_generate}.")
                
                # Button label shows the round number
                if st.button(f"Generate Pairings for Round {round_to_generate}", key="generate_next_round", disabled=is_locked_bool):
                    # Generate the next round pairings
                    tournament.generate_round_pairings(current_generated_rounds, initial=(current_generated_rounds == 0))
                    st.success(f"Pairings for Round {round_to_generate} generated successfully. Please scroll up to enter scores.")
                    st.rerun()
            else:
                # Message when the previous round is not yet complete
                st.warning(f"Results for Round {current_generated_rounds} must be entered and saved before generating Round {round_to_generate}.")
        
        st.markdown("---")
        
        # --- Export Data ---
        st.subheader("Export Data")
        export_col1, export_col2 = st.columns(2)
        
        # Export CSV
        csv_filename = export_to_csv(tournament, st.session_state.tournament_name)
        if csv_filename:
            with open(csv_filename, "r", newline="") as f:
                csv_data = f.read().encode('utf-8')
            export_col1.download_button(
                label="Download CSV ⬇️",
                data=csv_data,
                file_name=csv_filename,
                mime="text/csv",
                key="download_csv"
            )

        # Export Excel
        excel_filename = export_to_excel(tournament, st.session_state.tournament_name)
        if excel_filename:
            with open(excel_filename, "rb") as f:
                excel_data = f.read()
            export_col2.download_button(
                label="Download Excel ⬇️",
                data=excel_data,
                file_name=excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel"
            )


if __name__ == '__main__':
    main()