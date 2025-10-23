import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
import json
from datetime import datetime
from collections import Counter
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Database and JSON file paths
DB_PATH = os.getenv("TOURNAMENT_DB_PATH", "tournament.db")
JSON_EXPORT_PATH = "tournaments_export.json"

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

# --- Database Functions ---

def get_db_mtime(db_path=DB_PATH):
    try:
        return os.path.getmtime(db_path)
    except FileNotFoundError:
        return 0

def init_db(db_path=DB_PATH):
    try:
        logger.info(f"Using database path: {db_path}")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, date TEXT)''')
                     
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
        logger.info(f"Database initialized successfully at {db_path}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        st.error(f"Database initialization error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        st.error(f"Unexpected error: {e}")
        return None

def save_to_db(tournament, tournament_name, conn):
    try:
        c = conn.cursor()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        c.execute("SELECT id FROM tournaments WHERE name = ?", (tournament_name,))
        existing_id = c.fetchone()

        if existing_id:
            tournament_id = existing_id[0]
            c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament_id,))
            c.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament_id,))
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
        c.execute("SELECT COUNT(*) FROM tournaments")
        count = c.fetchone()[0]
        logger.debug(f"Number of tournaments after save: {count}")
        c.execute("SELECT id, name, date FROM tournaments")
        tournaments = c.fetchall()
        logger.debug(f"Tournaments after save: {tournaments}")
        
        # Auto-export to JSON after save
        export_success = export_tournaments_to_json(tournament_id)
        if export_success:
            logger.info(f"Auto-exported tournaments to {JSON_EXPORT_PATH}")
            st.success(f"Tournament '{tournament_name}' saved and exported to JSON! Download and commit to GitHub.")
        else:
            logger.error("Failed to auto-export tournaments to JSON")
            st.error("Failed to export tournaments to JSON. Download manually if needed.")
        
        st.cache_data.clear()
        logger.info(f"Tournament '{tournament_name}' saved with ID {tournament_id}")
        return tournament_id
    except sqlite3.Error as e:
        logger.error(f"Database error on save: {e}")
        st.error(f"Database error on save: {e}")
        conn.rollback()
        return None
    except Exception as e:
        logger.error(f"Unexpected error on save: {e}")
        st.error(f"Unexpected error on save: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def delete_tournament_from_db(tournament_id, db_path=DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament_id,))
        c.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament_id,))
        c.execute("DELETE FROM tournaments WHERE id = ?", (tournament_id,))
        
        conn.commit()
        st.cache_data.clear()
        logger.info(f"Tournament ID {tournament_id} deleted successfully")
        
        # Re-export JSON after deletion
        export_success = export_tournaments_to_json(tournament_id)
        if export_success:
            logger.info(f"Updated {JSON_EXPORT_PATH} after deleting tournament ID {tournament_id}")
        else:
            logger.error("Failed to update JSON export after deletion")
            st.error("Failed to update JSON export after deletion")
        
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error on delete: {e}")
        st.error(f"Database error on delete: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error on delete: {e}")
        st.error(f"Unexpected error on delete: {e}")
        return False
    finally:
        conn.close()

@st.cache_data(show_spinner="Refreshing tournament list...")
def load_tournaments_list(db_mtime, db_path=DB_PATH, _cache_buster=str(uuid.uuid4())):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, date FROM tournaments ORDER BY date DESC")
        tournaments = c.fetchall()
        conn.close()
        
        logger.debug(f"Raw tournaments from database: {tournaments}")
        
        if not tournaments:
            logger.warning("No tournaments found in the database")
            st.warning("No tournaments found in the database. Create and save a tournament to populate the list.")
            return []
        
        name_counts = Counter(t[1] for t in tournaments)
        result_list = []
        
        for t_id, t_name, t_date in tournaments:
            display_name = t_name
            if name_counts[t_name] > 1:
                display_name = f"{t_name} ({t_date.split(' ')[0]})"
            result_list.append((t_id, display_name))
        
        logger.info(f"Loaded {len(result_list)} tournaments for dropdown")
        return result_list
    except sqlite3.Error as e:
        logger.error(f"Error loading tournaments list: {e}")
        st.error(f"Error loading tournaments list: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error loading tournaments list: {e}")
        st.error(f"Unexpected error loading tournaments list: {e}")
        return []

def load_tournament_data(tournament_id, db_path=DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("SELECT name FROM tournaments WHERE id = ?", (tournament_id,))
        result = c.fetchone()
        if not result:
            logger.error(f"No tournament found with ID {tournament_id}")
            st.error(f"No tournament found with ID {tournament_id}")
            conn.close()
            return None, None, None
        tournament_name = result[0]

        c.execute("SELECT player_id, name, points, wins, hoops_scored, hoops_conceded FROM players WHERE tournament_id = ? ORDER BY player_id", (tournament_id,))
        player_data = c.fetchall()
        
        if not player_data:
            logger.error(f"No players found for tournament ID {tournament_id}")
            st.error(f"No players found for tournament ID {tournament_id}")
            conn.close()
            return None, None, None
        
        player_map = {}
        for p_id, name, points, wins, hs, hc in player_data:
            player = Player(p_id, name)
            player.points = points
            player.wins = wins
            player.hoops_scored = hs
            player.hoops_conceded = hc
            player_map[p_id] = player
        
        players_list = list(player_map.values())

        c.execute("SELECT MAX(round_num) FROM matches WHERE tournament_id = ?", (tournament_id,))
        num_rounds_query = c.fetchone()
        num_rounds = (num_rounds_query[0] + 1) if num_rounds_query[0] is not None else 1
        
        tournament = SwissTournament(players_list, num_rounds)
        tournament.rounds = [[] for _ in range(num_rounds)]
        
        c.execute("SELECT round_num, match_num, player1_id, player2_id, hoops1, hoops2 FROM matches WHERE tournament_id = ? ORDER BY round_num, match_num", (tournament_id,))
        match_data = c.fetchall()

        for r_num, m_num, p1_id, p2_id, h1, h2 in match_data:
            p1 = player_map.get(p1_id)
            p2 = player_map.get(p2_id) if p2_id != -1 else None
            
            if p1 is None:
                logger.warning(f"Player ID {p1_id} not found for match in round {r_num}, match {m_num}")
                st.warning(f"Player ID {p1_id} not found for match in round {r_num}, match {m_num}")
                continue

            if p2 is not None:
                p1.add_opponent(p2_id)
                p2.add_opponent(p1_id)

            match = Match(p1, p2)
            match.result = (h1, h2)
            
            while len(tournament.rounds) <= r_num:
                tournament.rounds.append([])
            
            if len(tournament.rounds[r_num]) <= m_num:
                tournament.rounds[r_num].extend([None] * (m_num - len(tournament.rounds[r_num]) + 1))
            
            tournament.rounds[r_num][m_num] = match

        conn.close()
        logger.info(f"Tournament ID {tournament_id} loaded successfully")
        return tournament, tournament_name, num_rounds
    except sqlite3.Error as e:
        logger.error(f"Database error loading tournament {tournament_id}: {e}")
        st.error(f"Database error loading tournament {tournament_id}: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"Unexpected error loading tournament {tournament_id}: {e}")
        st.error(f"Unexpected error loading tournament {tournament_id}: {e}")
        return None, None, None

# --- JSON Export/Import Functions ---

def export_tournaments_to_json(excluded_id=None):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id, name, date FROM tournaments")
        tournaments = c.fetchall()
        
        export_data = []
        for t_id, name, date in tournaments:
            if excluded_id and t_id == excluded_id:
                continue
                
            c.execute("SELECT player_id, name, points, wins, hoops_scored, hoops_conceded FROM players WHERE tournament_id = ?", (t_id,))
            players = c.fetchall()
            
            c.execute("SELECT round_num, match_num, player1_id, player2_id, hoops1, hoops2 FROM matches WHERE tournament_id = ?", (t_id,))
            matches = c.fetchall()
            
            export_data.append({
                "id": t_id,
                "name": name,
                "date": date,
                "players": [
                    {
                        "player_id": p[0],
                        "name": p[1],
                        "points": p[2],
                        "wins": p[3],
                        "hoops_scored": p[4],
                        "hoops_conceded": p[5]
                    } for p in players
                ],
                "matches": [
                    {
                        "round_num": m[0],
                        "match_num": m[1],
                        "player1_id": m[2],
                        "player2_id": m[3],
                        "hoops1": m[4],
                        "hoops2": m[5]
                    } for m in matches
                ]
            })
        
        conn.close()
        
        with open(JSON_EXPORT_PATH, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        return True
    except (sqlite3.Error, IOError) as e:
        logger.error(f"Error exporting tournaments to JSON: {e}")
        return False

def import_tournaments_from_json(file, db_path=DB_PATH):
    try:
        data = json.load(file)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        for tournament in data:
            c.execute("SELECT id FROM tournaments WHERE id = ?", (tournament['id'],))
            if c.fetchone():
                c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament['id'],))
                c.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament['id'],))
                c.execute("DELETE FROM tournaments WHERE id = ?", (tournament['id'],))
            
            c.execute("INSERT INTO tournaments (id, name, date) VALUES (?, ?, ?)", 
                     (tournament['id'], tournament['name'], tournament['date']))
            
            c.executemany("INSERT INTO players (tournament_id, player_id, name, points, wins, hoops_scored, hoops_conceded) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(tournament['id'], p['player_id'], p['name'], p['points'], p['wins'], p['hoops_scored'], p['hoops_conceded']) for p in tournament['players']])
            
            c.executemany("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, hoops1, hoops2) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         [(tournament['id'], m['round_num'], m['match_num'], m['player1_id'], m['player2_id'], m['hoops1'], m['hoops2']) for m in tournament['matches']])
        
        conn.commit()
        conn.close()
        st.cache_data.clear()
        logger.info("Tournaments imported from JSON successfully")
        return True
    except (sqlite3.Error, json.JSONDecodeError) as e:
        logger.error(f"Error importing tournaments from JSON: {e}")
        st.error(f"Error importing tournaments from JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error importing tournaments: {e}")
        st.error(f"Unexpected error importing tournaments: {e}")
        return False

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
        logger.error(f"Error writing CSV: {e}")
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
        logger.error(f"Error writing Excel: {e}")
        st.error(f"Error writing Excel: {e}")
        return None

# --- Streamlit UI and Logic ---

def _update_session_state_to_int(text_key, result_key, min_value, max_value):
    raw_value = st.session_state[text_key]
    
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
    
    if not raw_value:
        st.session_state[result_key] = 0
    else:
        try:
            num = int(raw_value)
            if num < min_value:
                st.session_state[result_key] = min_value
            elif num > max_value:
                st.session_state[result_key] = max_value
            else:
                st.session_state[result_key] = num
        except ValueError:
            st.session_state[result_key] = 0

def number_input_simple(key, min_value=0, max_value=26, step=1, label="", disabled=False):
    text_key = f"{key}_text"
    result_key = f"{key}_result"
    
    current_value_int = st.session_state.get(result_key, 0)
    
    if text_key not in st.session_state or st.session_state[text_key] == "":
        display_value = "" if current_value_int == 0 else str(current_value_int)
    else:
        display_value = st.session_state[text_key]

    st.text_input(
        label,
        value=display_value,
        max_chars=2,
        key=text_key,
        help="Enter score. Max 26.",
        disabled=disabled,
        on_change=lambda: _update_session_state_to_int(text_key, result_key, min_value, max_value)
    )
    
    return int(st.session_state.get(result_key, 0))

def load_selected_tournament(selected_id):
    try:
        tournament, tournament_name, num_rounds = load_tournament_data(selected_id)
        if tournament is None:
            st.session_state.tournament = None
            st.session_state.tournament_name = "New Tournament"
            st.session_state.players = []
            st.session_state.num_rounds = 3
            st.session_state.loaded_id = None
            return
        
        for key in list(st.session_state.keys()):
            if key.startswith(("hoops1_", "hoops2_")):
                del st.session_state[key]
        
        st.session_state.tournament = tournament
        st.session_state.tournament_name = tournament_name
        st.session_state.num_rounds = num_rounds
        st.session_state.players = [p.name for p in tournament.players]
        st.session_state.loaded_id = selected_id
        st.success(f"Tournament '{tournament_name}' loaded successfully.")
    except Exception as e:
        logger.error(f"Error loading tournament {selected_id}: {e}")
        st.error(f"Error loading tournament: {e}")
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3
        st.session_state.loaded_id = None

def handle_lock_change():
    st.session_state._lock_changed = True

def check_database_content(db_path=DB_PATH):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'tournaments')")
        if not c.fetchone()[0]:
            conn.close()
            return "Tournaments table does not exist."
        
        c.execute("SELECT id, name, date FROM tournaments ORDER BY date DESC")
        tournaments = c.fetchall()
        conn.close()
        
        if not tournaments:
            return "No tournaments found in the database."
        
        return f"Found {len(tournaments)} tournaments: {tournaments}"
    except sqlite3.Error as e:
        return f"Error checking database: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"

def auto_import_json():
    """Check for tournaments_export.json on startup and import it."""
    if os.path.exists(JSON_EXPORT_PATH):
        try:
            with open(JSON_EXPORT_PATH, 'rb') as f:
                if import_tournaments_from_json(f):
                    logger.info(f"Auto-imported tournaments from {JSON_EXPORT_PATH}")
                    st.session_state['auto_import_status'] = f"Restored tournaments from {JSON_EXPORT_PATH}"
                    st.cache_data.clear()
                else:
                    logger.error(f"Failed to auto-import from {JSON_EXPORT_PATH}")
                    st.session_state['auto_import_status'] = f"Failed to restore tournaments from {JSON_EXPORT_PATH}"
        except Exception as e:
            logger.error(f"Error during auto-import: {e}")
            st.session_state['auto_import_status'] = f"Error during auto-import: {e}"
    else:
        logger.info(f"No {JSON_EXPORT_PATH} found for auto-import")
        st.session_state['auto_import_status'] = f"No {JSON_EXPORT_PATH} found"

def main():
    st.set_page_config(layout="wide", page_title="Croquet Tournament Manager")
    logger.info(f"Starting app with database path: {DB_PATH}")
    
    # Auto-import JSON on startup
    if 'auto_import_status' not in st.session_state:
        auto_import_json()
    
    st.markdown("""
        <style>
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
        
        div.stButton > button:hover,
        .stButton button:hover,
        button[data-testid="stBaseButton-secondaryFormSubmit"]:hover {
            background-color: #388E3C !important;
            border: 1px solid #2E7D32 !important;
        }

        button[data-testid="stBaseButton-secondaryFormSubmit"] {
            background-color: #4CAF50 !important;
            color: white !important;
            border: 1px solid #388E3C !important;
        }
        
        div[data-testid^="stTextInput"] input {
            color: black !important; 
            font-weight: bold;
            text-align: center;
        }
        
        .stForm div[data-testid="stFormSubmitButton"] {
            width: 100%;
        }
        
        .round-complete-text {
            color: #4CAF50;
            font-weight: bold;
            margin-top: -10px;
            padding-left: 10px;
        }
        </style>
        """, unsafe_allow_html=True)
    
    st.title("Croquet Tournament Manager 🏏 (Swiss System, No Draws)")

    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3
        st.session_state.loaded_id = None
        st.session_state.is_locked = "Unlocked"
        st.session_state._lock_changed = False
        st.session_state.auto_import_status = ""
        
    is_locked_bool = (st.session_state.is_locked == "Locked")
    
    if st.session_state._lock_changed:
        st.session_state._lock_changed = False
        if is_locked_bool:
            st.toast("🔒 Tournament Input is Locked", icon="🚫")
        else:
            st.toast("🔓 Tournament Input is Unlocked", icon="✅")
        st.rerun()

    with st.sidebar:
        st.header("App Status")
        
        # Display auto-import status
        if st.session_state.auto_import_status:
            if "Restored" in st.session_state.auto_import_status:
                st.success(st.session_state.auto_import_status)
            else:
                st.warning(st.session_state.auto_import_status)
        
        st.session_state.is_locked = st.radio(
            "Tournament Input Status",
            ["Unlocked", "Locked"],
            key="lock_radio",
            horizontal=True,
            help="**Locked** prevents entry of scores and submission of results on this device.",
            on_change=handle_lock_change
        )
        
        st.header("Load Saved Tournament")
        conn = init_db()
        if conn is None:
            st.error("Failed to initialize database. Check database path and permissions.")
        else:
            conn.close()
        
        st.subheader("Debug Database")
        if st.button("Check Database Content", key="check_db_button"):
            db_content = check_database_content()
            st.info(f"Database status: {db_content}")
        
        if st.button("Refresh Tournament List", key="refresh_tournaments"):
            logger.info("Manual cache invalidation triggered")
            st.cache_data.clear()
            st.success("Tournament list refreshed!")
            st.rerun()
        
        st.subheader("Import/Export Tournaments")
        if os.path.exists(JSON_EXPORT_PATH):
            with open(JSON_EXPORT_PATH, 'rb') as f:
                st.download_button(
                    label="Download JSON Export",
                    data=f.read(),
                    file_name=JSON_EXPORT_PATH,
                    mime="application/json",
                    key="download_json_button"
                )
        
        uploaded_file = st.file_uploader("Import Tournaments from JSON", type=["json"], key="import_json")
        if uploaded_file and st.button("Import JSON", key="import_json_button"):
            if import_tournaments_from_json(uploaded_file):
                st.success("Tournaments imported successfully! Reloading page...")
                # Update JSON export after import
                export_tournaments_to_json()
                st.rerun()
            else:
                st.error("Failed to import tournaments.")
        
        st.subheader("Sync with GitHub")
        st.markdown("""
            **To persist tournaments:**
            1. Click "Save Tournament" to save and auto-export to JSON.
            2. Download `tournaments_export.json` (above).
            3. Commit to your GitHub repository with:
            ```bash
            git add tournaments_export.json
            git commit -m "Update tournament data"
            git push origin main
            ```
            4. On app restart, ensure `tournaments_export.json` is in the repository for auto-import.
        """)
        
        db_mtime = get_db_mtime()
        tournaments_list = load_tournaments_list(db_mtime)
        
        display_list = ["--- New Tournament ---"] + [t[1] for t in tournaments_list]
        id_map = {t[1]: t[0] for t in tournaments_list}
        
        default_index = 0
        if st.session_state.loaded_id:
            for idx, (t_id, display_name) in enumerate(tournaments_list):
                if t_id == st.session_state.loaded_id:
                    default_index = idx + 1
                    break
        
        selected_display = st.selectbox(
            "Select a tournament to load:",
            display_list,
            index=default_index,
            key="load_selectbox"
        )
        
        selected_id = id_map.get(selected_display)
        
        if selected_display == "--- New Tournament ---" and st.session_state.tournament:
            if st.button("Start New Tournament", key="new_tournament_button"):
                logger.info("Starting new tournament")
                st.session_state.tournament = None
                st.session_state.tournament_name = "New Tournament"
                st.session_state.players = []
                st.session_state.num_rounds = 3
                st.session_state.loaded_id = None
                st.rerun()
        elif selected_id and selected_id != st.session_state.loaded_id:
            logger.info(f"Loading tournament ID {selected_id}")
            load_selected_tournament(selected_id)
            st.rerun()
        
        if selected_id:
            st.markdown("---")
            st.warning("PERMANENT ACTION")
            if st.button(f"Delete '{selected_display}'", key="delete_button", disabled=is_locked_bool):
                logger.info(f"Attempting to delete tournament ID {selected_id}")
                if delete_tournament_from_db(selected_id):
                    st.success(f"Tournament '{selected_display}' deleted. Reloading page...")
                    if st.session_state.loaded_id == selected_id:
                        st.session_state.tournament = None
                        st.session_state.tournament_name = "New Tournament"
                        st.session_state.players = []
                        st.session_state.num_rounds = 3
                        st.session_state.loaded_id = None
                    st.rerun()
                else:
                    st.error("Failed to delete the tournament.")

    if not st.session_state.tournament or not st.session_state.players:
        expander_state = True
    else:
        expander_state = False
        
    with st.expander("Create/Setup Tournament", expanded=expander_state):
        with st.form("tournament_form_setup"):
            st.session_state.tournament_name = st.text_input("Tournament Name", value=st.session_state.tournament_name, disabled=is_locked_bool)
            player_input = st.text_area("Enter player names (one per line)", "\n".join(st.session_state.players), disabled=is_locked_bool)
            st.session_state.num_rounds = st.number_input("Number of Rounds", min_value=1, max_value=10, value=st.session_state.num_rounds, step=1, disabled=is_locked_bool)
            submitted = st.form_submit_button("Create Tournament", disabled=is_locked_bool)

            if submitted and st.session_state.tournament_name and player_input:
                st.session_state.players = [name.strip() for name in player_input.split('\n') if name.strip()]
                if len(st.session_state.players) < 2:
                    st.error("At least 2 players are required!")
                else:
                    for key in list(st.session_state.keys()):
                        if key.startswith(("hoops1_", "hoops2_")):
                            if key in st.session_state:
                                del st.session_state[key]
                    
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.session_state.loaded_id = None
                    logger.info(f"New tournament created: {st.session_state.tournament_name}")
                    st.success("Tournament created! All pairings generated. Scroll down to enter results.")
                    st.rerun()

    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        st.header(f"Active Tournament: {st.session_state.tournament_name}")

        st.subheader("Match Results & Input")
        
        score_keys_to_update = []
        
        for round_num in range(tournament.num_rounds):
            pairings = tournament.get_round_pairings(round_num)
            for match_num, match in enumerate(pairings):
                if match and match.player2 is not None:
                    hoops1_key_root = f"hoops1_r{round_num}_m{match_num}"
                    hoops2_key_root = f"hoops2_r{round_num}_m{match_num}"
                    
                    result1_key = f"{hoops1_key_root}_result"
                    result2_key = f"{hoops2_key_root}_result"
                    
                    current_hoops1, current_hoops2 = match.get_scores()
                    
                    if result1_key not in st.session_state:
                        st.session_state[result1_key] = current_hoops1
                    
                    if result2_key not in st.session_state:
                        st.session_state[result2_key] = current_hoops2
                        
                    score_keys_to_update.append((round_num, match_num, hoops1_key_root, hoops2_key_root))

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
                        
                    try:
                        match_info = next((r, m, k1, k2) 
                                        for r, m, k1, k2 in score_keys_to_update 
                                        if r == round_num and m == round_pairings.index(match))
                    except StopIteration:
                        continue

                    hoops1_key_root = match_info[2]
                    hoops2_key_root = match_info[3]
                    
                    with (match_col1 if match_display_num % 2 != 0 else match_col2):
                        
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
                                
                        st.markdown("---")
                        match_display_num += 1
            
            if is_round_complete:
                st.markdown('<p class="round-complete-text">✅ All games played for this round</p>', unsafe_allow_html=True)

        with st.form("results_submission_form"):
            st.markdown("---")
            results_submitted = st.form_submit_button("Recalculate Standings", disabled=is_locked_bool)
            st.markdown("---")
            
            if results_submitted:
                for p in tournament.players:
                    p.points = 0
                    p.wins = 0
                    p.hoops_scored = 0
                    p.hoops_conceded = 0
                
                for round_num, match_num, hoops1_key_root, hoops2_key_root in score_keys_to_update:
                    match = tournament.get_round_pairings(round_num)[match_num]
                    
                    if match is None or match.player2 is None: continue
                    
                    result1_key = f"{hoops1_key_root}_result"
                    result2_key = f"{hoops2_key_root}_result"
                    
                    hoops1 = st.session_state.get(result1_key, 0)
                    hoops2 = st.session_state.get(result2_key, 0)
                    
                    if hoops1 == hoops2 and hoops1 > 0:
                        st.warning(f"Round {round_num+1} Match {match_num+1}: Scores for {match.player1.name} and {match.player2.name} are equal ({hoops1}-{hoops2}). No points or wins were awarded.")
                    
                    match.result = None 
                    match.set_result(hoops1, hoops2)

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

        st.subheader("Current Standings 🏆")
        standings = tournament.get_standings()
        standings_data = [{
            'Rank': i+1,
            'Name': p.name,
            'Wins': p.wins,
            'Points': p.points,
            'Net Hoops': p.hoops_scored - p.hoops_conceded,
            'Hoops Scored': p.hoops_scored
        } for i, p in enumerate(standings)]
        st.dataframe(pd.DataFrame(standings_data), use_container_width=True)
        
        st.subheader("Save and Export")
        
        col_save, col_export1, col_export2 = st.columns(3)

        with col_save:
            if st.button("Save Tournament", key="save_button", disabled=is_locked_bool):
                conn = init_db()
                if conn:
                    tournament_id = save_to_db(tournament, st.session_state.tournament_name, conn)
                    if tournament_id:
                        st.session_state.loaded_id = tournament_id
                        st.success(f"Tournament '{st.session_state.tournament_name}' saved and exported to JSON! Download and commit to GitHub.")
                        st.rerun()
                    else:
                        st.error("Failed to save tournament to database.")
                else:
                    st.error("Failed to initialize database.")

        with col_export1:
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