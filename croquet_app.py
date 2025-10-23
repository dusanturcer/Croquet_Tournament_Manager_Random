import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
import os
from datetime import datetime

# --- Player and Match Classes (Omitted for brevity, assume they are correct) ---
# ... [Classes Player, Match, SwissTournament are here] ...
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
# ...

class Match:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.result = None

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
# ...

class SwissTournament:
    def __init__(self, players, num_rounds):
        self.players = [Player(i, name) for i, name in enumerate(players)]
        self.num_rounds = num_rounds
        self.rounds = []
        self.generate_round_pairings(0, initial=True)
        for round_num in range(1, self.num_rounds):
            self.generate_round_pairings(round_num)

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
                if p2 is None:
                    pass
                else:
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

            if round_num + 1 < self.num_rounds:
                 self.generate_round_pairings(round_num + 1)
        else:
            st.error(f"Invalid round_num {round_num} or match_num {match_num}")

    def get_standings(self):
        return sorted(self.players, key=lambda p: (p.points, p.hoops_scored - p.hoops_conceded, p.hoops_scored), reverse=True)

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []
# ... [Database and Export functions are here] ...
def init_db(db_path='tournament.db'):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                 (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (tournament_id INTEGER, player_id INTEGER, name TEXT, points INTEGER, wins INTEGER,
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

def export_to_csv(tournament, tournament_name):
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{tournament_name}_{timestamp}.csv"
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Round', 'Match', 'Player 1', 'Player 2', 'Hoops 1', 'Hoops 2'])
            for round_num, round_pairings in enumerate(tournament.rounds):
                for match_num, match in enumerate(round_pairings):
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


# --- Callback Functions (NEW) ---

def decrement_score(key, step, min_value):
    """Callback to safely decrement score in session state."""
    temp_key = f"{key}_temp"
    current_value = st.session_state.get(temp_key, 0)
    st.session_state[temp_key] = max(min_value, current_value - step)

def increment_score(key, step, max_value):
    """Callback to safely increment score in session state."""
    temp_key = f"{key}_temp"
    current_value = st.session_state.get(temp_key, 0)
    st.session_state[temp_key] = min(max_value, current_value + step)


# --- Streamlit UI and Logic ---

# Custom number input with + and - buttons (UPDATED)
def number_input_with_buttons(label, key, value=0, min_value=0, max_value=26, step=1):
    temp_key = f"{key}_temp"

    # Initialize session state for this key
    if temp_key not in st.session_state:
        st.session_state[temp_key] = int(value)

    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        # Use on_click callback instead of st.experimental_rerun()
        st.button(
            "−", 
            key=f"minus_{key}",
            on_click=decrement_score, 
            args=(key, step, min_value) # Pass arguments to the callback
        ) 

    with col2:
        # The st.number_input handles its own internal re-run/state update
        st.session_state[temp_key] = st.number_input(
            label,
            min_value=min_value,
            max_value=max_value,
            value=st.session_state[temp_key], # Use the session state value
            step=step,
            format="%d",
            key=f"{key}_input" # Unique key for number_input
        )
        
    with col3:
        # Use on_click callback instead of st.experimental_rerun()
        st.button(
            "+", 
            key=f"plus_{key}",
            on_click=increment_score, 
            args=(key, step, max_value) # Pass arguments to the callback
        )
    
    # Return the current session state value
    return int(st.session_state[temp_key])


def main():
    st.set_page_config(layout="wide", page_title="Croquet Tournament Manager")
    st.title("Croquet Tournament Manager 🏏 (BYE=0 Points, No Draws)")

    # Initialize session state
    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3

    # --- Tournament Setup (Unchanged) ---
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
                        if key.endswith(("_temp", "_input")):
                            del st.session_state[key]
                            
                    st.session_state.tournament = SwissTournament(st.session_state.players, int(st.session_state.num_rounds))
                    st.success("Tournament created! Pairings generated for all rounds. Scroll down to enter results.")

    # --- Tournament Management ---
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        
        st.header(f"Tournament: {st.session_state.tournament_name}")

        # --- Match Results & Pairing Display ---
        st.subheader("Match Results & Input")
        
        score_keys_to_update = [] 

        for round_num in range(tournament.num_rounds):
            st.markdown(f"#### Round {round_num + 1} Pairings")
            pairings = tournament.get_round_pairings(round_num)
            
            for match_num, match in enumerate(pairings):
                st.markdown("---")
                if match.player2 is None:
                    st.info(f"**Match {match_num + 1}:** {match.player1.name} gets a **BYE** (0 points awarded)")
                    continue
                
                col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
                
                hoops1_key = f"hoops1_r{round_num}_m{match_num}"
                hoops2_key = f"hoops2_r{round_num}_m{match_num}"
                
                score_keys_to_update.append((round_num, match_num, hoops1_key, hoops2_key))

                with col1:
                    st.markdown(f"**Match {match_num + 1}:**")
                    st.markdown(f"**{match.player1.name}** vs **{match.player2.name}**")
                    st.write("*(Hoop scores must differ to award a win point)*")
                
                with col2:
                    number_input_with_buttons(
                        label=f"Hoops for {match.player1.name}",
                        key=hoops1_key,
                        value=int(match.get_scores()[0]),
                        min_value=0, max_value=26
                    )
                    
                with col3:
                    number_input_with_buttons(
                        label=f"Hoops for {match.player2.name}",
                        key=hoops2_key,
                        value=int(match.get_scores()[1]),
                        min_value=0, max_value=26
                    )
                
                with col4:
                    if match.result:
                        status = "Draw (0 pts)"
                        if match.result[0] > match.result[1]:
                            status = f"Winner: {match.player1.name}"
                        elif match.result[1] > match.result[0]:
                            status = f"Winner: {match.player2.name}"
                        st.metric(label="Current Score", value=f"{match.result[0]} - {match.result[1]}", delta=status)
                    else:
                        st.metric(label="Current Score", value="Not Recorded")


        # --- The Submission Form (Unchanged) ---
        with st.form("results_submission_form"):
            st.markdown("---")
            results_submitted = st.form_submit_button("Update All Match Results and Recalculate Standings/Pairings")
            st.markdown("---")
            
            if results_submitted:
                for round_num, match_num, hoops1_key_root, hoops2_key_root in score_keys_to_update:
                    match = tournament.get_round_pairings(round_num)[match_num]
                    
                    hoops1_key = f"{hoops1_key_root}_temp"
                    hoops2_key = f"{hoops2_key_root}_temp"
                    
                    hoops1 = st.session_state.get(hoops1_key, 0)
                    hoops2 = st.session_state.get(hoops2_key, 0)
                    
                    if hoops1 == hoops2:
                        st.warning(f"Round {round_num+1} Match {match_num+1}: Scores for {match.player1.name} and {match.player2.name} are equal ({hoops1}-{hoops2}). No points or wins were awarded for this match.")
                        
                    tournament.record_result(round_num, match_num, hoops1, hoops2)
                    
                st.success("All results updated! Standings and subsequent round pairings recalculated.")
                st.experimental_rerun() 

        # --- Standings (Unchanged) ---
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

        # --- Save and Export (Unchanged) ---
        st.subheader("Save and Export")
        
        col_save, col_export1, col_export2 = st.columns(3)

        with col_save:
            if st.button("Save Tournament to Database"):
                conn = init_db()
                save_to_db(tournament, st.session_state.tournament_name, conn)
                conn.close()
                st.success("Tournament saved to database!")

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