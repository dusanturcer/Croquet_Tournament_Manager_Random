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
        return self.result if self.result else (0, 0)

class SwissTournament:
    def __init__(self, players_names_or_objects, num_rounds):
        # Handle initialization from names (new tournament) or Player objects (loaded tournament)
        if all(isinstance(p, str) for p in players_names_or_objects):
            self.players = [Player(i, name) for i, name in enumerate(players_names_or_objects)]
            self.rounds = []
            for round_num in range(num_rounds):
                initial = (round_num == 0)
                self.generate_round_pairings(round_num, initial=initial) 
        else:
            self.players = players_names_or_objects
            self.rounds = [] # Rounds will be populated by load_tournament_data
            
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

# ----------------------------------------------------------------------
# --- Database Functions (Modified for name-only display) ---
# ----------------------------------------------------------------------

DB_PATH = 'tournament.db'

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
    # (Save logic remains the same: finds existing entry by name or creates a new one)
    try:
        c = conn.cursor()
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Check if tournament name already exists
        c.execute("SELECT id FROM tournaments WHERE name = ?", (tournament_name,))
        existing_id = c.fetchone()

        if existing_id:
            tournament_id = existing_id[0]
            # Delete old data associated with this tournament ID
            c.execute("DELETE FROM players WHERE tournament_id = ?", (tournament_id,))
            c.execute("DELETE FROM matches WHERE tournament_id = ?", (tournament_id,))
            c.execute("UPDATE tournaments SET date = ? WHERE id = ?", (date, tournament_id))
        else:
            c.execute("INSERT INTO tournaments (name, date) VALUES (?, ?)", (tournament_name, date))
            tournament_id = c.lastrowid

        player_data = [(tournament_id, p.id, p.name, p.points, p.wins, p.hoops_scored, p.hoops_conceded) for p in tournament.players]
        c.executemany("INSERT INTO players (tournament_id, player_id, name, points, wins, hoops_scored, hoops_conceded) VALUES (?, ?, ?, ?, ?, ?, ?)", player_data)

        match_data = []
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                hoops1, hoops2 = match.get_scores()
                player2_id = match.player2.id if match.player2 else -1
                match_data.append((tournament_id, round_num, match_num, match.player1.id, player2_id, hoops1, hoops2))

        c.executemany("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, hoops1, hoops2) VALUES (?, ?, ?, ?, ?, ?, ?)", match_data)

        conn.commit()
    except sqlite3.Error as e:
        st.error(f"Database error on save: {e}")
        conn.rollback() 

def load_tournaments_list(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    # Fetch all tournaments, ordered by most recently saved (important for stable display if names are duplicated)
    c.execute("SELECT id, name, date FROM tournaments ORDER BY date DESC")
    tournaments = c.fetchall()
    conn.close()
    
    # Store list of names and dates to check for duplicates
    name_date_list = [(t[1], t[2].split(' ')[0]) for t in tournaments]
    name_counts = Counter(t[0] for t in name_date_list)

    result_list = []
    
    # Format: [(id, "Name"), ...] OR [(id, "Name (Date)") if duplicated]
    for t_id, t_name, t_date in tournaments:
        display_name = t_name
        
        # If the name is duplicated, append the date to distinguish them in the dropdown
        if name_counts[t_name] > 1:
            display_name = f"{t_name} ({t_date.split(' ')[0]})"
            
        result_list.append((t_id, display_name))
        
    return result_list

def load_tournament_data(tournament_id, db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Load Tournament Metadata
    c.execute("SELECT name FROM tournaments WHERE id = ?", (tournament_id,))
    tournament_name = c.fetchone()[0]

    # 2. Load Players
    c.execute("SELECT player_id, name, points, wins, hoops_scored, hoops_conceded FROM players WHERE tournament_id = ? ORDER BY player_id", (tournament_id,))
    player_data = c.fetchall()
    
    player_map = {}
    
    # Reconstruct Player objects and stats
    for p_id, name, points, wins, hs, hc in player_data:
        player = Player(p_id, name)
        player.points = points
        player.wins = wins
        player.hoops_scored = hs
        player.hoops_conceded = hc
        player_map[p_id] = player
        
    players_list = list(player_map.values())

    # 3. Instantiate the tournament object
    num_rounds_query = c.execute("SELECT MAX(round_num) FROM matches WHERE tournament_id = ?", (tournament_id,)).fetchone()
    num_rounds = (num_rounds_query[0] + 1) if num_rounds_query[0] is not None else 1
    
    tournament = SwissTournament(players_list, num_rounds)
    
    # 4. Load Matches
    c.execute("SELECT round_num, match_num, player1_id, player2_id, hoops1, hoops2 FROM matches WHERE tournament_id = ? ORDER BY round_num, match_num", (tournament_id,))
    match_data = c.fetchall()

    tournament.rounds = [[] for _ in range(num_rounds)]
    
    # Reconstruct Match objects and results
    for r_num, m_num, p1_id, p2_id, h1, h2 in match_data:
        p1 = player_map.get(p1_id)
        p2 = player_map.get(p2_id) if p2_id != -1 else None # -1 signifies BYE
        
        if p1 is None:
            continue

        if p2 is not None:
            p1.add_opponent(p2_id)
            p2.add_opponent(p1_id)

        match = Match(p1, p2)
        match.result = (h1, h2)
        
        while len(tournament.rounds) <= r_num:
            tournament.rounds.append([])
            
        # Ensure we append correctly, especially if the match data isn't perfectly dense
        if len(tournament.rounds[r_num]) <= m_num:
             tournament.rounds[r_num].extend([None] * (m_num - len(tournament.rounds[r_num]) + 1))
        
        tournament.rounds[r_num][m_num] = match


    conn.close()
    return tournament, tournament_name, num_rounds

# --- Export Functions (Omitted for brevity) ---

def export_to_csv(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.csv"
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Round', 'Match', 'Player 1', 'Player 2', 'Hoops 1', 'Hoops 2'])
            for round_num, round_pairings in enumerate(tournament.rounds):
                for match_num, match in enumerate(round_pairings):
                    if match is None: continue # Skip None entries if round data was sparse
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
                if match is None: continue # Skip None entries
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
# --- Streamlit UI and Logic ---
# ----------------------------------------------------------------------

def number_input_simple(key, min_value=0, max_value=26, step=1, label=""):
    input_key = f"{key}_input"

    st.number_input(
        label,
        min_value=min_value,
        max_value=max_value,
        step=step,
        format="%d",
        key=input_key
    )
    
    return int(st.session_state.get(input_key, 0))

def load_selected_tournament(selected_id):
    if selected_id:
        try:
            tournament, tournament_name, num_rounds = load_tournament_data(selected_id)
            
            # Reset existing hoop input state keys to avoid conflicts with new matches
            for key in list(st.session_state.keys()):
                if key.endswith(("_input")):
                    del st.session_state[key]
            
            st.session_state.tournament = tournament
            st.session_state.tournament_name = tournament_name
            st.session_state.num_rounds = num_rounds
            st.session_state.players = [p.name for p in tournament.players]
            st.success(f"Tournament '{tournament_name}' loaded successfully.")
            
        except Exception as e:
            st.error(f"Error loading tournament data: {e}")
            st.session_state.tournament = None

def main():
    st.set_page_config(layout="wide", page_title="Croquet Tournament Manager")
    st.title("Croquet Tournament Manager 🏏 (Swiss System, No Draws)")

    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3

    # --- Sidebar for Loading Saved Tournaments ---
    with st.sidebar:
        st.header("Load Saved Tournament")
        init_db()
        tournaments_list = load_tournaments_list()
        
        # Prepare lists for the selectbox and mapping
        display_list = ["--- New Tournament ---"] + [t[1] for t in tournaments_list]
        id_map = {t[1]: t[0] for t in tournaments_list} # Map Display Name -> ID
        
        # Determine the default index for the selectbox
        default_index = 0
        current_name = st.session_state.tournament_name
        
        # If a tournament is currently loaded, try to select it in the dropdown
        for idx, display_name in enumerate(display_list):
            # Check for exact match (if not duplicated) or match of base name (if duplicated)
            base_name = display_name.split(' (')[0]
            if base_name == current_name:
                default_index = idx
                break
        
        selected_display = st.selectbox(
            "Select a tournament to load:",
            display_list,
            index=default_index,
            key="load_selectbox"
        )
        
        # --- Logic for handling the selection ---
        if selected_display == "--- New Tournament ---":
            if st.session_state.tournament:
                if st.button("Start New Tournament"):
                    # Use a unique key for button to prevent Streamlit warnings if placed in a loop
                    st.session_state.tournament = None
                    st.session_state.tournament_name = "New Tournament"
                    st.session_state.players = []
                    st.session_state.num_rounds = 3
                    st.rerun()
        else:
            selected_id = id_map.get(selected_display)
            
            # Check if the selected tournament is *different* from the one currently loaded
            is_different_selection = (selected_display.split(' (')[0] != st.session_state.tournament_name) or (not st.session_state.tournament)
            
            if is_different_selection:
                # Use the selected ID to load the tournament immediately without a button
                load_selected_tournament(selected_id)
                st.rerun()

    # --- Main Content: Tournament Setup ---
    with st.expander("Create/Setup Tournament", expanded=not st.session_state.tournament):
        with st.form("tournament_form"):
            st.session_state.tournament_name = st.text_input("Tournament Name", value=st.session_state.tournament_name)
            player_input = st.text_area("Enter player names (one per line)", "\n".join(st.session_state.players))
            st.session_state.num_rounds = st.number_input("Number of Rounds", min_value=1, max_value=10, value=st.session_state.num_rounds, step=1)
            submitted = st.form_submit_button("Create Tournament")

            if submitted and st.session_state.tournament_name and player_input:
                st.session_state.players = [name.strip() for name in player_input.split('\n') if name.strip()]
                if len(st.session_state.players) < 2:
                    st.error("At least 2 players are required!")
                else:
                    for key in list(st.session_state.keys()):
                        if key.endswith(("_input")):
                            del st.session_state[key]
                            
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.success("Tournament created! All pairings generated. Scroll down to enter results.")

    # --- Main Content: Tournament Management ---
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        st.header(f"Active Tournament: {st.session_state.tournament_name}")

        # --- Match Results & Pairing Display ---
        st.subheader("Match Results & Input")
        
        score_keys_to_update = [] 
        
        # 1. Synchronization and Key Generation Block
        for round_num in range(tournament.num_rounds):
            pairings = tournament.get_round_pairings(round_num)
            for match_num, match in enumerate(pairings):
                if match and match.player2 is not None:
                    hoops1_key = f"hoops1_r{round_num}_m{match_num}"
                    hoops2_key = f"hoops2_r{round_num}_m{match_num}"
                    input1_key = f"{hoops1_key}_input"
                    input2_key = f"{hoops2_key}_input"
                    
                    current_hoops1, current_hoops2 = match.get_scores()
                    
                    if input1_key not in st.session_state:
                        st.session_state[input1_key] = current_hoops1
                    
                    if input2_key not in st.session_state:
                        st.session_state[input2_key] = current_hoops2
                        
                    score_keys_to_update.append((round_num, match_num, hoops1_key, hoops2_key))

        # 2. Display Block with Compact Layout, NO BYE info, and TWO COLUMNS
        for round_num in range(tournament.num_rounds):
            round_pairings = tournament.get_round_pairings(round_num)
            
            # Filter non-BYE matches
            non_bye_matches = [match for match in round_pairings if match and match.player2 is not None]
            
            if not non_bye_matches:
                continue

            round_label = f"Round {round_num + 1} ({len(non_bye_matches)} matches)"
            expanded_state = (round_num == 0)
            
            with st.expander(round_label, expanded=expanded_state):
                
                match_col1, match_col2 = st.columns(2)
                match_display_num = 1
                
                for i, match in enumerate(round_pairings):
                    if match is None or match.player2 is None:
                        continue 
                        
                    current_match_col = match_col1 if match_display_num % 2 != 0 else match_col2
                    
                    with current_match_col:
                        try:
                            match_info = next((r, m, k1, k2) 
                                             for r, m, k1, k2 in score_keys_to_update 
                                             if r == round_num and m == round_pairings.index(match))
                        except StopIteration:
                            continue

                        hoops1_key = match_info[2]
                        hoops2_key = match_info[3]
                        
                        col_num, col_p1, col_h1, col_h2, col_p2, col_status = st.columns([0.5, 2, 1, 1, 2, 1.5])
                        
                        with col_num:
                            st.markdown(f"**{match_display_num}:**")
                            
                        with col_p1:
                            st.markdown(f"**<h4 style='text-align: left;'>{match.player1.name}</h4>**", unsafe_allow_html=True)
                            
                        with col_h1:
                            number_input_simple(key=hoops1_key)
                        
                        with col_h2:
                            number_input_simple(key=hoops2_key)
                        
                        with col_p2:
                            st.markdown(f"**<h4 style='text-align: left;'>{match.player2.name}</h4>**", unsafe_allow_html=True)
                            
                        with col_status:
                            input1_key = f"{hoops1_key}_input"
                            input2_key = f"{hoops2_key}_input"
                            
                            live_hoops1 = st.session_state.get(input1_key, 0)
                            live_hoops2 = st.session_state.get(input2_key, 0)

                            status_text = f"{live_hoops1} - {live_hoops2}"
                            
                            if live_hoops1 > live_hoops2:
                                status_delta = "P1 Wins"
                            elif live_hoops2 > live_hoops1:
                                status_delta = "P2 Wins"
                            elif live_hoops1 == live_hoops2 and (live_hoops1 > 0):
                                status_delta = "Draw (0 pts)"
                            else:
                                status_delta = " "

                            st.metric(label="Score", value=status_text, delta=status_delta)
                                
                        current_match_col.markdown("---")
                        match_display_num += 1


        # --- The Submission Form ---
        with st.form("results_submission_form"):
            st.markdown("---")
            results_submitted = st.form_submit_button("Update All Match Results and Recalculate Standings/Pairings")
            st.markdown("---")
            
            if results_submitted:
                for round_num, match_num, hoops1_key_root, hoops2_key_root in score_keys_to_update:
                    match = tournament.get_round_pairings(round_num)[match_num]
                    
                    if match is None: continue # Skip None entries
                    
                    hoops1_key = f"{hoops1_key_root}_input"
                    hoops2_key = f"{hoops2_key_root}_input"
                    
                    hoops1 = st.session_state.get(hoops1_key, 0)
                    hoops2 = st.session_state.get(hoops2_key, 0)
                    
                    if hoops1 == hoops2 and match.player2 is not None:
                        st.warning(f"Round {round_num+1} Match {match_num+1}: Scores for {match.player1.name} and {match.player2.name} are equal ({hoops1}-{hoops2}). No points or wins were awarded for this match.")
                        
                    tournament.record_result(round_num, match_num, hoops1, hoops2)

                st.success("All visible match results updated! Standings recalculated.")

        # --- Standings ---
        st.subheader("Current Standings 🏆")
        standings = tournament.get_standings()
        standings_data = [{
            'Rank': i+1,
            'Name': p.name,
            'Wins': p.wins,
            'Net Hoops': p.hoops_scored - p.hoops_conceded,
            'Hoops Scored': p.hoops_scored
        } for i, p in enumerate(standings)]
        st.dataframe(pd.DataFrame(standings_data), use_container_width=True)

        # --- Save and Export ---
        st.subheader("Save and Export")
        
        col_save, col_export1, col_export2 = st.columns(3)

        with col_save:
            if st.button("Save Tournament to Database (Overwrites existing name)"):
                conn = init_db()
                save_to_db(tournament, st.session_state.tournament_name, conn)
                conn.close()
                st.success(f"Tournament '{st.session_state.tournament_name}' saved to database! Reload the page or click 'Load Saved Tournament' to refresh the list.")

        with col_export1:
            if st.button("Generate CSV"):
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
            if st.button("Generate Excel"):
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