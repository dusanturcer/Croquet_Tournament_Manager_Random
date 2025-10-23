import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
from datetime import datetime
from collections import Counter

# --- Player and Match Classes (Unchanged) ---

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
                initial = (round_num == 0)
                self.generate_round_pairings(round_num, initial=initial) 
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
            available_players = self.players.copy()
            random.shuffle(available_players) 
        else:
            available_players = self.get_standings()
        
        used_players = set()
        
        for i in range(len(available_players)):
            p1 = available_players[i]
            if p1.id in used_players:
                continue
            
            best_p2 = None
            for j in range(i + 1, len(available_players)):
                p2 = available_players[j]
                if p2.id not in used_players and p2.id not in p1.opponents:
                    best_p2 = p2
                    break
            
            if best_p2:
                round_pairings.append(Match(p1, best_p2))
                used_players.add(p1.id)
                used_players.add(best_p2.id)
                p1.add_opponent(best_p2.id)
                best_p2.add_opponent(p1.id)
            
        remaining_players = [p for p in available_players if p.id not in used_players]
        if remaining_players:
            bye_player = remaining_players[0]
            round_pairings.append(Match(bye_player, None))
        
        self.rounds[round_num] = round_pairings
        
        if len(used_players) + len(remaining_players) != len(self.players):
             st.warning(f"Warning: Only {len(used_players) + len(remaining_players)}/{len(self.players)} players paired in round {round_num + 1} due to opponent restrictions.")

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

    # 🔑 FIX: ADDED METHOD TO COUNT GAMES PLAYED 🔑
    def get_games_played(self, player_id):
        count = 0
        for round_pairings in self.rounds:
            for match in round_pairings:
                # Only count matches that have a result recorded
                if match and match.result is not None:
                    # Check if the player was player 1 and it wasn't a BYE
                    if match.player1.id == player_id and match.player2 is not None:
                        count += 1
                    # Check if the player was player 2
                    elif match.player2 and match.player2.id == player_id:
                        count += 1
        return count

# ----------------------------------------------------------------------
# --- Database Functions (Unchanged) ---
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
    num_rounds = (num_rounds_query[0] + 1) if num_rounds_query[0] is not None else 1
    
    # Create the tournament object with the correct list size for rounds
    tournament = SwissTournament(players_list, num_rounds)
    tournament.rounds = [[] for _ in range(num_rounds)] 
    
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

    conn.close()
    return tournament, tournament_name, num_rounds

# --- Export Functions (Unchanged) ---

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
    # Read the raw string value from the st.text_input key
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
    
    # Define two separate keys: one for the raw string input, one for the clean integer result
    text_key = f"{key}_text" 
    result_key = f"{key}_result" 

    # 1. Get current clean integer result. 
    current_value_int = st.session_state.get(result_key, 0)
    
    # 2. Determine the string to DISPLAY in the box. 
    if text_key not in st.session_state or st.session_state[text_key] == "":
        display_value = "" if current_value_int == 0 else str(current_value_int)
    else:
        display_value = st.session_state[text_key]


    # 3. Render the st.text_input using text_key for its string value.
    st.text_input(
        label,
        value=display_value,
        max_chars=2, 
        key=text_key, # This key stores the raw string input (must be a string)
        help="Enter score. Max 26.",
        
        # Pass the disabled status here
        disabled=disabled,
        
        # Callback updates the separate result_key (must store an int)
        on_change=lambda: _update_session_state_to_int(text_key, result_key, min_value, max_value)
    )
    
    # 4. Return the clean integer result.
    return int(st.session_state.get(result_key, 0))


def load_selected_tournament(selected_id):
    if selected_id:
        try:
            tournament, tournament_name, num_rounds = load_tournament_data(selected_id)
            
            # Clear all old match score states for the previous tournament
            for key in list(st.session_state.keys()):
                # Check for ALL keys related to score inputs
                if key.startswith(("hoops1_", "hoops2_")):
                    del st.session_state[key]
            
            st.session_state.tournament = tournament
            st.session_state.tournament_name = tournament_name
            st.session_state.num_rounds = num_rounds
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
    # This block executes immediately upon rerun, allowing the toast to be seen.
    if st.session_state._lock_changed:
        st.session_state._lock_changed = False  # Reset flag
        
        if is_locked_bool:
            # Displays the floating toast bar
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
        
        # Action: Start New Tournament (This should always be allowed)
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
            if st.button(f"🗑️ Delete '{selected_display}' from DB", key="delete_button", disabled=is_locked_bool):
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
                        # Clear ALL score keys (text_key and result_key)
                        if key.startswith(("hoops1_", "hoops2_")):
                            if key in st.session_state:
                                del st.session_state[key]
                            
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.session_state.loaded_id = None # Mark as a new, unsaved tournament
                    st.success("Tournament created! All pairings generated. Scroll down to enter results.")
                    st.rerun() # Rerun to update the page structure

    # --- Main Content: Tournament Management ---
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        st.header(f"Active Tournament: {st.session_state.tournament_name}")

        # --- Match Results & Pairing Display (Inputs now OUTSIDE the form) ---
        st.subheader("Match Results & Input")
        
        score_keys_to_update = [] 
        
        # Pre-process all keys and initialize session state before the form runs
        for round_num in range(tournament.num_rounds):
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
        for round_num in range(tournament.num_rounds):
            round_pairings = tournament.get_round_pairings(round_num)
            
            non_bye_matches = [match for match in round_pairings if match and match.player2 is not None]
            
            if not non_bye_matches:
                continue
            
            is_round_complete = all(sum(m.get_scores()) > 0 for m in non_bye_matches)

            round_label = f"Round {round_num + 1} ({len(non_bye_matches)} matches)"
            
            expanded_state = not is_round_complete and (round_num == len(tournament.rounds) - 1 or round_num == 0)

            with st.expander(round_label, expanded=expanded_state):
                
                match_col1, match_col2 = st.columns(2)
                match_display_num = 1
                
                for i, match in enumerate(round_pairings):
                    if match is None or match.player2 is None:
                        continue 
                        
                    current_match_col = match_col1 if match_display_num % 2 != 0 else match_col2
                    
                    try:
                        match_info = next((r, m, k1, k2) 
                                        for r, m, k1, k2 in score_keys_to_update 
                                        if r == round_num and m == round_pairings.index(match))
                    except StopIteration:
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
                            # Pass the disabled state to the input function
                            live_hoops1 = number_input_simple(key=hoops1_key_root, disabled=is_locked_bool)
                        
                        with col_h2:
                            # Pass the disabled state to the input function
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
            
            # Show completion text if the round is complete 
            if is_round_complete:
                st.markdown('<p class="round-complete-text">✅ All games played for this round</p>', unsafe_allow_html=True)
            # --------------------------------------------------------

        # SUBMISSION FORM (ONLY CONTAINS THE BUTTON)
        with st.form("results_submission_form"):
            st.markdown("---")
            # DISABLE THE SUBMIT BUTTON IF LOCKED
            results_submitted = st.form_submit_button("Update All Match Results and Recalculate Standings/Pairings", disabled=is_locked_bool)
            st.markdown("---")
            
            if results_submitted:
                
                # Reset all player stats before reapplying scores
                for p in tournament.players:
                    p.points = 0
                    p.wins = 0
                    p.hoops_scored = 0
                    p.hoops_conceded = 0
                
                # Reapply results using the values from the new result_key in session state
                for round_num, match_num, hoops1_key_root, hoops2_key_root in score_keys_to_update:
                    match = tournament.get_round_pairings(round_num)[match_num]
                    
                    if match is None or match.player2 is None: continue
                    
                    # Use the clean integer result keys
                    result1_key = f"{hoops1_key_root}_result"
                    result2_key = f"{hoops2_key_root}_result"
                    
                    # Ensure we use the cleaned integer value from the session state
                    hoops1 = st.session_state.get(result1_key, 0)
                    hoops2 = st.session_state.get(result2_key, 0)
                    
                    if hoops1 == hoops2 and hoops1 > 0:
                        st.warning(f"Round {round_num+1} Match {match_num+1}: Scores for {match.player1.name} and {match.player2.name} are equal ({hoops1}-{hoops2}). No points or wins were awarded.")
                    
                    # Temporarily reset match.result to None to allow record_result to function as a set/reset
                    match.result = None 
                    
                    # This applies the score AND updates player stats
                    match.set_result(hoops1, hoops2)

                # After updating results, check for round completion and generate the next round if necessary
                current_max_round = len(tournament.rounds)
                
                next_round_to_generate = -1
                all_rounds_complete_for_gen = True
                
                for r_idx in range(current_max_round):
                    pairings = tournament.get_round_pairings(r_idx)
                    non_bye_matches = [m for m in pairings if m and m.player2]
                    
                    if any(m.result is None for m in non_bye_matches):
                        all_rounds_complete_for_gen = False
                        break
                
                if all_rounds_complete_for_gen and current_max_round < tournament.num_rounds:
                    next_round_to_generate = current_max_round
                
                if current_max_round == 0 and tournament.num_rounds > 0:
                     next_round_to_generate = 0

                if next_round_to_generate != -1 and next_round_to_generate < tournament.num_rounds:
                    tournament.generate_round_pairings(next_round_to_generate, initial=False)
                    st.success(f"Round {next_round_to_generate + 1} pairings generated based on new standings.")
                    st.rerun()

                st.success("All match results processed! Standings recalculated.")
                st.rerun()


        # --------------------------------------------------------------------
        # --- Standings (Modified) ---
        st.subheader("Current Standings 🏆")
        standings = tournament.get_standings()
        
        # --- MODIFIED STANDINGS DATA GENERATION ---
        standings_data = [{
            # 'Rank' is intentionally excluded
            'Name': p.name,
            'Games Played': tournament.get_games_played(p.id), # NEW COLUMN - Now working with added method
            'Wins': p.wins,
            'Points': p.points,
            'Net Hoops': p.hoops_scored - p.hoops_conceded,
            'Hoops Scored': p.hoops_scored,
            'Hoops Conceded': p.hoops_conceded # NEW COLUMN at the end
        } for p in standings]
        
        # Display the modified DataFrame
        st.dataframe(pd.DataFrame(standings_data), use_container_width=True)
        # --------------------------------------------------------------------
        
        # --------------------------------------------------------------------
        # --- Save and Export (Disabled if Locked) ---
        st.subheader("Save and Export")
        
        col_save, col_export1, col_export2 = st.columns(3)

        with col_save:
            # DISABLE SAVE BUTTON IF LOCKED
            if st.button("Save Tournament", key="save_button", disabled=is_locked_bool):
                conn = init_db()
                tournament_id = save_to_db(tournament, st.session_state.tournament_name, conn)
                conn.close()
                if tournament_id:
                    st.session_state.loaded_id = tournament_id
                    st.success(f"Tournament '{st.session_state.tournament_name}' saved to database!")
                    st.rerun()

        with col_export1:
            # EXPORT is generally a "read-only" action, so typically NOT disabled by a lock.
            if st.button("Generate CSV", key="csv_button"):
                filename = export_to_csv(tournament, st.session_state.tournament_name)
                if filename:
                    with open(filename, 'rb') as f:
                        st.download_button(
                            label="Download CSV",
                            data=f.read(),
                            file_name=filename,
                            mime='text/csv'
                        )
                    os.remove(filename)

        with col_export2:
            # EXPORT is generally a "read-only" action, so typically NOT disabled by a lock.
            if st.button("Generate Excel", key="excel_button"):
                filename = export_to_excel(tournament, st.session_state.tournament_name)
                if filename:
                    with open(filename, 'rb') as f:
                        st.download_button(
                            label="Download Excel",
                            data=f.read(),
                            file_name=filename,
                            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                        )
                    os.remove(filename)

if __name__ == "__main__":
    main()