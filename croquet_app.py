import streamlit as st
import pandas as pd
import sqlite3
import random
import itertools
import csv
from openpyxl import load_workbook
from openpyxl.styles import Alignment
from datetime import datetime

class Player:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.points = 0
        self.opponents = set()

    def add_opponent(self, opponent_id):
        self.opponents.add(opponent_id)

    def __repr__(self):
        return f"Player(id={self.id}, name={self.name}, points={self.points})"

class Match:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.result = None

    def set_result(self, result):
        self.result = result
        if self.player2 is None:  # Bye
            self.player1.points += 1
            return
        if result == 1:
            self.player1.points += 1
        elif result == 2:
            self.player2.points += 1
        elif result == 0:
            self.player1.points += 0.5
            self.player2.points += 0.5

    def __repr__(self):
        return f"Match({self.player1.name} vs {self.player2.name if self.player2 else 'BYE'}, result={self.result})"

class SwissTournament:
    def __init__(self, players, num_rounds):
        self.players = [Player(i, name) for i, name in enumerate(players)]
        self.num_rounds = num_rounds
        self.rounds = []
        self.generate_all_pairings()

    def generate_all_pairings(self):
        self.rounds = []
        player_opponents = {p.id: set() for p in self.players}

        for round_num in range(self.num_rounds):
            round_pairings = []
            available_players = [p for p in self.players]
            random.shuffle(available_players)
            used_players = set()

            # Generate possible pairs avoiding previous opponents
            possible_pairs = []
            for i in range(len(available_players)):
                for j in range(i + 1, len(available_players)):
                    p1 = available_players[i]
                    p2 = available_players[j]
                    if p2.id not in player_opponents[p1.id]:
                        possible_pairs.append((p1, p2))

            random.shuffle(possible_pairs)

            # Select pairs greedily
            pair_index = 0
            while len(used_players) < len(available_players) and pair_index < len(possible_pairs):
                p1, p2 = possible_pairs[pair_index]
                if p1.id not in used_players and p2.id not in used_players:
                    round_pairings.append(Match(p1, p2))
                    used_players.add(p1.id)
                    used_players.add(p2.id)
                    player_opponents[p1.id].add(p2.id)
                    player_opponents[p2.id].add(p1.id)
                pair_index += 1

            # Handle remaining players (odd number or couldn't pair)
            remaining_players = [p for p in available_players if p.id not in used_players]
            if remaining_players:
                bye_player = random.choice(remaining_players)
                round_pairings.append(Match(bye_player, None))
                used_players.add(bye_player.id)

            self.rounds.append(round_pairings)

            if len(used_players) < len(self.players):
                st.warning(f"Only {len(used_players)}/{len(self.players)} players paired in round {round_num + 1}")

    def record_result(self, round_num, match_num, result):
        if 0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num]):
            match = self.rounds[round_num][match_num]
            match.set_result(result)
        else:
            st.error(f"Invalid round_num {round_num} or match_num {match_num}")

    def get_standings(self):
        return sorted(self.players, key=lambda p: (-p.points, p.id))

    def get_round_pairings(self, round_num):
        if 0 <= round_num < len(self.rounds):
            return self.rounds[round_num]
        return []

    def __repr__(self):
        return f"SwissTournament(players={len(self.players)}, rounds={self.num_rounds})"

# Database setup
def init_db():
    conn = sqlite3.connect('tournament.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tournaments
                 (id INTEGER PRIMARY KEY, name TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS players
                 (tournament_id INTEGER, player_id INTEGER, name TEXT, points REAL,
                  PRIMARY KEY (tournament_id, player_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS matches
                 (tournament_id INTEGER, round_num INTEGER, match_num INTEGER,
                  player1_id INTEGER, player2_id INTEGER, result INTEGER)''')
    conn.commit()
    return conn

# Save tournament data to database
def save_to_db(tournament, tournament_name, conn):
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO tournaments (name, date) VALUES (?, ?)", (tournament_name, date))
    tournament_id = c.lastrowid

    for player in tournament.players:
        c.execute("INSERT INTO players (tournament_id, player_id, name, points) VALUES (?, ?, ?, ?)",
                  (tournament_id, player.id, player.name, player.points))

    for round_num, round_pairings in enumerate(tournament.rounds):
        for match_num, match in enumerate(round_pairings):
            player2_id = match.player2.id if match.player2 else None
            c.execute("INSERT INTO matches (tournament_id, round_num, match_num, player1_id, player2_id, result) VALUES (?, ?, ?, ?, ?, ?)",
                      (tournament_id, round_num, match_num, match.player1.id, player2_id, match.result))

    conn.commit()

# Export to CSV
def export_to_csv(tournament, tournament_name):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tournament_name}_{timestamp}.csv"
    with open(filename, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Round', 'Match', 'Player 1', 'Player 2', 'Result'])
        for round_num, round_pairings in enumerate(tournament.rounds):
            for match_num, match in enumerate(round_pairings):
                player2 = match.player2.name if match.player2 else 'BYE'
                result = match.result if match.result is not None else 'Pending'
                writer.writerow([round_num + 1, match_num + 1, match.player1.name, player2, result])
    return filename

# Export to Excel
def export_to_excel(tournament, tournament_name):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{tournament_name}_{timestamp}.xlsx"
    data = []
    for round_num, round_pairings in enumerate(tournament.rounds):
        for match_num, match in enumerate(round_pairings):
            player2 = match.player2.name if match.player2 else 'BYE'
            result = match.result if match.result is not None else 'Pending'
            data.append({
                'Round': round_num + 1,
                'Match': match_num + 1,
                'Player 1': match.player1.name,
                'Player 2': player2,
                'Result': result
            })
    df = pd.DataFrame(data)
    df.to_excel(filename, index=False)
    
    # Format Excel file
    wb = load_workbook(filename)
    ws = wb.active
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ws.max_column):
        for cell in row:
            cell.alignment = Alignment(horizontal='center')
    wb.save(filename)
    return filename

# Streamlit app
def main():
    st.title("Swiss Tournament Manager")

    # Initialize session state
    if 'tournament' not in st.session_state:
        st.session_state.tournament = None
        st.session_state.tournament_name = ""
        st.session_state.players = []
        st.session_state.num_rounds = 3

    # Input form
    with st.form("tournament_form"):
        st.session_state.tournament_name = st.text_input("Tournament Name", value=st.session_state.tournament_name)
        player_input = st.text_area("Enter player names (one per line)", "\n".join(st.session_state.players))
        st.session_state.num_rounds = st.number_input("Number of Rounds", min_value=1, max_value=10, value=st.session_state.num_rounds)
        submitted = st.form_submit_button("Create Tournament")

        if submitted and st.session_state.tournament_name and player_input:
            st.session_state.players = [name.strip() for name in player_input.split('\n') if name.strip()]
            if len(st.session_state.players) < 2:
                st.error("At least 2 players are required!")
            else:
                st.session_state.tournament = SwissTournament(st.session_state.players, st.session_state.num_rounds)
                st.success("Tournament created!")

    # Display pairings and record results
    if st.session_state.tournament:
        tournament = st.session_state.tournament
        conn = init_db()

        for round_num in range(tournament.num_rounds):
            st.subheader(f"Round {round_num + 1} Pairings")
            pairings = tournament.get_round_pairings(round_num)
            for match_num, match in enumerate(pairings):
                with st.container():
                    col1, col2, col3 = st.columns([2, 2, 1])
                    if match.player2 is None:
                        col1.write(f"{match.player1.name} gets a bye")
                    else:
                        col1.write(f"{match.player1.name} vs {match.player2.name}")
                        with col2:
                            result = st.radio(
                                f"Result for {match.player1.name} vs {match.player2.name}",
                                options=["Pending", f"{match.player1.name} wins", f"{match.player2.name} wins", "Draw"],
                                key=f"result_{round_num}_{match_num}",
                                index=0
                            )
                            if result != "Pending":
                                result_map = {
                                    f"{match.player1.name} wins": 1,
                                    f"{match.player2.name} wins": 2,
                                    "Draw": 0
                                }
                                tournament.record_result(round_num, match_num, result_map[result])

        # Save to database
        if st.button("Save Tournament"):
            save_to_db(tournament, st.session_state.tournament_name, conn)
            st.success("Tournament saved to database!")
            conn.close()

        # Display standings
        st.subheader("Current Standings")
        standings = tournament.get_standings()
        standings_data = [{'Name': p.name, 'Points': p.points} for p in standings]
        st.dataframe(pd.DataFrame(standings_data))

        # Export options
        col_export1, col_export2 = st.columns(2)
        with col_export1:
            if st.button("Export to CSV"):
                filename = export_to_csv(tournament, st.session_state.tournament_name)
                st.download_button(
                    label="Download CSV",
                    data=open(filename, 'rb').read(),
                    file_name=filename,
                    mime='text/csv'
                )
        with col_export2:
            if st.button("Export to Excel"):
                filename = export_to_excel(tournament, st.session_state.tournament_name)
                st.download_button(
                    label="Download Excel",
                    data=open(filename, 'rb').read(),
                    file_name=filename,
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )

if __name__ == "__main__":
    main()