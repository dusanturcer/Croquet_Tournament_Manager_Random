import streamlit as st
import pandas as pd
import psycopg2
import random
import csv
import os
from datetime import datetime
from collections import Counter
import uuid
import logging

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# DB connection – uses DATABASE_URL (Supavisor recommended)
# --------------------------------------------------------------------------- #
def get_connection():
    url = os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL not set! Add it in **Secrets** (Streamlit) or **Environment** (Render).")
        raise RuntimeError("DATABASE_URL not set in environment")
    return psycopg2.connect(url, sslmode="require")

def init_schema(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tournaments (
                id   SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                date TEXT NOT NULL
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                tournament_id   INTEGER NOT NULL,
                player_id       INTEGER NOT NULL,
                name            TEXT    NOT NULL,
                points          INTEGER DEFAULT 0,
                wins            INTEGER DEFAULT 0,
                hoops_scored    INTEGER DEFAULT 0,
                hoops_conceded  INTEGER DEFAULT 0,
                PRIMARY KEY (tournament_id, player_id),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS matches (
                tournament_id INTEGER NOT NULL,
                round_num     INTEGER NOT NULL,
                match_num     INTEGER NOT NULL,
                player1_id    INTEGER NOT NULL,
                player2_id    INTEGER,
                hoops1        INTEGER DEFAULT 0,
                hoops2        INTEGER DEFAULT 0,
                PRIMARY KEY (tournament_id, round_num, match_num),
                FOREIGN KEY (tournament_id) REFERENCES tournaments(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
        logger.info("DB schema ensured")
    except Exception as e:
        logger.error(f"Schema init error: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()

# --------------------------------------------------------------------------- #
# Model classes
# --------------------------------------------------------------------------- #
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
        self.result = None

    def set_result(self, hoops1, hoops2):
        hoops1, hoops2 = int(hoops1), int(hoops2)
        if self.player2 is None:  # bye
            self.result = (hoops1, hoops2)
            return

        self.player1.hoops_scored   += hoops1
        self.player1.hoops_conceded += hoops2
        self.player2.hoops_scored   += hoops2
        self.player2.hoops_conceded += hoops1

        if hoops1 > hoops2:
            self.player1.wins   += 1
            self.player1.points += 1
        elif hoops2 > hoops1:
            self.player2.wins   += 1
            self.player2.points += 1

        self.result = (hoops1, hoops2)

    def get_scores(self):
        return self.result if self.result else (0, 0)

# --------------------------------------------------------------------------- #
# UNIVERSAL SWISS TOURNAMENT – works for 6, 8, 9, 10+ players
# --------------------------------------------------------------------------- #
class SwissTournament:
    def __init__(self, players_names_or_objects, num_rounds):
        if all(isinstance(p, str) for p in players_names_or_objects):
            self.players = [Player(i, name) for i, name in enumerate(players_names_or_objects)]
        else:
            self.players = players_names_or_objects

        self.n = len(self.players)
        self.num_rounds = num_rounds
        self.rounds = []
        self.opponents = {p.id: set() for p in self.players}
        self.bye_count = {p.id: 0 for p in self.players}  # Track bye fairness
        self._generate_all_rounds()

    def _get_next_bye_player(self, used):
        """Return player with fewest byes (tiebreak: lowest ID)"""
        candidates = [p for p in self.players if p.id not in used]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (self.bye_count[p.id], p.id))
        return candidates[0]

    def _generate_all_rounds(self):
        n = self.n
        is_even = n % 2 == 0

        # --- Round 1: Deterministic pairing ---
        first_round = []
        used = set()

        if is_even:
            for i in range(n // 2):
                p1 = self.players[i]
                p2 = self.players[n - 1 - i]
                first_round.append(Match(p1, p2))
                self.opponents[p1.id].add(p2.id)
                self.opponents[p2.id].add(p1.id)
                used.update([p1.id, p2.id])
        else:
            for i in range(n // 2):
                p1 = self.players[i]
                p2 = self.players[n - 1 - i]
                first_round.append(Match(p1, p2))
                self.opponents[p1.id].add(p2.id)
                self.opponents[p2.id].add(p1.id)
                used.update([p1.id, p2.id])
            bye_player = self._get_next_bye_player(used)
            if bye_player:
                first_round.append(Match(bye_player, None))
                self.bye_count[bye_player.id] += 1
                used.add(bye_player.id)

        self.rounds.append(first_round)

        # --- Rounds 2+ ---
        if is_even:
            top = self.players[:n//2]
            bottom = self.players[n//2:]
        else:
            all_players = self.players.copy()

        for rnd in range(1, self.num_rounds):
            round_matches = []
            used = set()

            if is_even:
                bottom = bottom[1:] + bottom[:1]
                pairs = [(top[i], bottom[i]) for i in range(n//2)]
            else:
                all_players = all_players[1:] + all_players[:1]
                pairs = []
                for i in range(n//2):
                    p1 = all_players[i]
                    p2 = all_players[i + n//2]
                    if p1.id != p2.id and p2.id not in self.opponents[p1.id]:
                        pairs.append((p1, p2))
                    else:
                        # Fallback: find any valid opponent
                        for cand in all_players:
                            if cand.id != p1.id and cand.id not in used and cand.id not in self.opponents[p1.id]:
                                pairs.append((p1, cand))
                                break
                        else:
                            # Last resort: any unused
                            for cand in all_players:
                                if cand.id != p1.id and cand.id not in used:
                                    pairs.append((p1, cand))
                                    break

            # Process pairs
            for p1, p2 in pairs:
                if p1.id == p2.id or p2.id in self.opponents[p1.id]:
                    available = [p for p in self.players if p.id not in used and p.id not in self.opponents[p1.id]]
                    if available:
                        p2 = available[0]
                    else:
                        continue

                round_matches.append(Match(p1, p2))
                self.opponents[p1.id].add(p2.id)
                self.opponents[p2.id].add(p1.id)
                used.update([p1.id, p2.id])

            # Add bye if odd
            if not is_even:
                bye_player = self._get_next_bye_player(used)
                if bye_player:
                    round_matches.append(Match(bye_player, None))
                    self.bye_count[bye_player.id] += 1

            self.rounds.append(round_matches)

    def record_result(self, round_num, match_num, hoops1, hoops2):
        if not (0 <= round_num < len(self.rounds) and 0 <= match_num < len(self.rounds[round_num])):
            return
        match = self.rounds[round_num][match_num]
        old1, old2 = match.get_scores()
        if match.result and match.player2:
            match.player1.hoops_scored   -= old1
            match.player1.hoops_conceded -= old2
            match.player2.hoops_scored   -= old2
            match.player2.hoops_conceded -= old1
            if old1 > old2:
                match.player1.wins   -= 1
                match.player1.points -= 1
            elif old2 > old1:
                match.player2.wins   -= 1
                match.player2.points -= 1
        match.set_result(hoops1, hoops2)

    def get_standings(self):
        return sorted(
            self.players,
            key=lambda p: (p.points, p.hoops_scored - p.hoops_conceded, p.hoops_scored),
            reverse=True,
        )

    def get_round_pairings(self, round_num):
        return self.rounds[round_num] if 0 <= round_num < len(self.rounds) else []

# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
def get_db_mtime():
    return datetime.now().timestamp()

def save_to_db(tournament, tournament_name):
    conn = get_connection()
    try:
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id FROM tournaments WHERE name=%s", (tournament_name,))
        row = c.fetchone()
        if row:
            tid = row[0]
            c.execute("DELETE FROM players WHERE tournament_id=%s", (tid,))
            c.execute("DELETE FROM matches WHERE tournament_id=%s", (tid,))
            c.execute("UPDATE tournaments SET name=%s, date=%s WHERE id=%s", (tournament_name, now, tid))
        else:
            c.execute("INSERT INTO tournaments (name,date) VALUES (%s,%s) RETURNING id", (tournament_name, now))
            tid = c.fetchone()[0]

        c.executemany(
            "INSERT INTO players (tournament_id,player_id,name,points,wins,hoops_scored,hoops_conceded) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(tid, p.id, p.name, p.points, p.wins, p.hoops_scored, p.hoops_conceded) for p in tournament.players]
        )

        match_rows = []
        for r, rnd in enumerate(tournament.rounds):
            for m, match in enumerate(rnd):
                if not match: continue
                h1, h2 = match.get_scores()
                p2id = match.player2.id if match.player2 else -1
                match_rows.append((tid, r, m, match.player1.id, p2id, h1, h2))
        c.executemany(
            "INSERT INTO matches (tournament_id,round_num,match_num,player1_id,player2_id,hoops1,hoops2) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            match_rows
        )
        conn.commit()
        st.cache_data.clear()
        logger.info(f"Saved tournament {tid}")
        return tid
    except Exception as e:
        logger.error(f"Save error: {e}")
        st.error(f"Save error: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def delete_tournament_from_db(tournament_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM players WHERE tournament_id=%s", (tournament_id,))
        c.execute("DELETE FROM matches WHERE tournament_id=%s", (tournament_id,))
        c.execute("DELETE FROM tournaments WHERE id=%s", (tournament_id,))
        conn.commit()
        st.cache_data.clear()
        return True
    except Exception as e:
        logger.error(f"Delete error: {e}")
        st.error(f"Delete error: {e}")
        return False
    finally:
        conn.close()

@st.cache_data(show_spinner="Loading tournament list…")
def load_tournaments_list(_db_mtime, _cache_buster=str(uuid.uuid4())):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name, date FROM tournaments ORDER BY date DESC")
        rows = c.fetchall()
        conn.close()
        if not rows: return []
        name_cnt = Counter(r[1] for r in rows)
        out = []
        for tid, name, date in rows:
            disp = name if name_cnt[name] == 1 else f"{name} ({date.split(' ')[0]})"
            out.append((tid, disp))
        return out
    except Exception as e:
        logger.error(f"Load list error: {e}")
        st.error(f"Load list error: {e}")
        return []

def load_tournament_data(tournament_id):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM tournaments WHERE id=%s", (tournament_id,))
        tname = c.fetchone()
        if not tname: return None, None, None
        tname = tname[0]

        c.execute("SELECT player_id, name, points, wins, hoops_scored, hoops_conceded FROM players WHERE tournament_id=%s ORDER BY player_id", (tournament_id,))
        player_rows = c.fetchall()
        player_map = {}
        for pid, name, pts, wins, hs, hc in player_rows:
            p = Player(pid, name)
            p.points = pts; p.wins = wins; p.hoops_scored = hs; p.hoops_conceded = hc
            player_map[pid] = p

        c.execute("SELECT MAX(round_num) FROM matches WHERE tournament_id=%s", (tournament_id,))
        max_r = c.fetchone()[0]
        num_rounds = (max_r + 1) if max_r is not None else 1

        tournament = SwissTournament(list(player_map.values()), num_rounds)
        tournament.rounds = [[] for _ in range(num_rounds)]

        c.execute("SELECT round_num, match_num, player1_id, player2_id, hoops1, hoops2 FROM matches WHERE tournament_id=%s ORDER BY round_num, match_num", (tournament_id,))
        for r, m, p1id, p2id, h1, h2 in c.fetchall():
            p1 = player_map.get(p1id)
            p2 = player_map.get(p2id) if p2id != -1 else None
            if p1 and p2:
                p1.add_opponent(p2.id)
                p2.add_opponent(p1.id)
            match = Match(p1, p2)
            match.result = (h1, h2)
            while len(tournament.rounds) <= r:
                tournament.rounds.append([])
            if len(tournament.rounds[r]) <= m:
                tournament.rounds[r].extend([None] * (m - len(tournament.rounds[r]) + 1))
            tournament.rounds[r][m] = match

        conn.close()
        return tournament, tname, num_rounds
    except Exception as e:
        logger.error(f"Load tournament error: {e}")
        st.error(f"Load tournament error: {e}")
        return None, None, None
    finally:
        conn.close()

# --------------------------------------------------------------------------- #
# Simple number input
# --------------------------------------------------------------------------- #
def _sync_text_to_int(text_key, int_key, mn, mx):
    raw = st.session_state.get(text_key, "")
    if isinstance(raw, str): raw = raw.strip()
    if not raw:
        st.session_state[int_key] = 0
        return
    try:
        v = int(raw)
        st.session_state[int_key] = max(mn, min(mx, v))
    except ValueError:
        st.session_state[int_key] = 0

def number_input_simple(key, min_value=0, max_value=26, label="", disabled=False):
    txt = f"{key}_txt"
    val = f"{key}_val"
    if val not in st.session_state: st.session_state[val] = 0
    if txt not in st.session_state:
        cur = st.session_state[val]
        st.session_state[txt] = "" if cur == 0 else str(cur)
    st.text_input(
        label, value=st.session_state[txt], max_chars=2, key=txt,
        disabled=disabled, help="0-26",
        on_change=_sync_text_to_int, args=(txt, val, min_value, max_value)
    )
    return int(st.session_state[val])

# --------------------------------------------------------------------------- #
# UI helpers
# --------------------------------------------------------------------------- #
def load_selected_tournament(tid):
    tournament, name, rounds = load_tournament_data(tid)
    if not tournament:
        st.session_state.tournament = None
        st.session_state.tournament_name = "New Tournament"
        st.session_state.players = []
        st.session_state.num_rounds = 3
        st.session_state.loaded_id = None
        return
    for k in list(st.session_state.keys()):
        if k.startswith(("hoops1_", "hoops2_")):
            del st.session_state[k]
    st.session_state.tournament = tournament
    st.session_state.tournament_name = name
    st.session_state.num_rounds = rounds
    st.session_state.players = [p.name for p bye in tournament.players]
    st.session_state.loaded_id = tid
    st.success(f"Loaded **{name}**")

def handle_lock_change():
    st.session_state._lock_changed = True

# --------------------------------------------------------------------------- #
# Main UI
# --------------------------------------------------------------------------- #
def main():
    st.set_page_config(layout="wide", page_title="Croquet Tournament Manager")
    logger.info("App start")

    # --- Ensure DB schema ---
    try:
        conn = get_connection()
        init_schema(conn)
        conn.close()
    except Exception as e:
        st.error(f"Failed to initialise database: {e}")
        st.stop()

    # --- Session state ---
    defaults = {
        "tournament": None, "tournament_name": "New Tournament",
        "players": [], "num_rounds": 3, "loaded_id": None,
        "is_locked": "Unlocked", "_lock_changed": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    locked = st.session_state.is_locked == "Locked"
    if st.session_state._lock_changed:
        st.session_state._lock_changed = False
        st.toast("Tournament Input is **Locked**" if locked else "Tournament Input is **Unlocked**")
        st.rerun()

    # --- Sidebar ---
    with st.sidebar:
        st.header("App Status")
        st.session_state.is_locked = st.radio(
            "Input", ["Unlocked", "Locked"], index=0 if not locked else 1,
            horizontal=True, help="**Locked** disables score entry.",
            on_change=handle_lock_change
        )

        st.header("Load Saved Tournament")
        if st.button("Refresh list"):
            st.cache_data.clear()
            st.rerun()

        tour_list = load_tournaments_list(get_db_mtime())
        options = ["--- New Tournament ---"] + [t[1] for t in tour_list]
        id_map = {t[1]: t[0] for t in tour_list}
        default_idx = 0
        if st.session_state.loaded_id:
            for i, (tid, disp) in enumerate(tour_list):
                if tid == st.session_state.loaded_id:
                    default_idx = i + 1
                    break
        sel_disp = st.selectbox("Select tournament", options, index=default_idx)
        sel_id = id_map.get(sel_disp)

        if sel_disp == "--- New Tournament ---" and st.session_state.tournament:
            if st.button("Start fresh"):
                for k in defaults: st.session_state[k] = defaults[k]
                st.rerun()
        elif sel_id and sel_id != st.session_state.loaded_id:
            load_selected_tournament(sel_id)
            st.rerun()

        if sel_id:
            st.markdown("---")
            if st.button(f"Delete **{sel_disp}**", disabled=locked):
                if delete_tournament_from_db(sel_id):
                    st.success("Deleted")
                    if st.session_state.loaded_id == sel_id:
                        for k in defaults: st.session_state[k] = defaults[k]
                    st.rerun()
                else:
                    st.error("Delete failed")

    # --- Create tournament ---
    expander_open = not bool(st.session_state.tournament)
    with st.expander("Create / Setup Tournament", expanded=expander_open):
        with st.form("setup_form"):
            st.session_state.tournament_name = st.text_input(
                "Tournament name", value=st.session_state.tournament_name, disabled=locked
            )
            players_txt = st.text_area(
                "Players (one per line)", "\n".join(st.session_state.players), disabled=locked
            )
            st.session_state.num_rounds = st.number_input(
                "Rounds", 1, 15, st.session_state.num_rounds, disabled=locked
            )
            if st.form_submit_button("Create", disabled=locked):
                new_players = [p.strip() for p in players_txt.splitlines() if p.strip()]
                if len(new_players) < 2:
                    st.error("Need >= 2 players")
                else:
                    for k in list(st.session_state.keys()):
                        if k.startswith(("hoops1_", "hoops2_")):
                            del st.session_state[k]
                    st.session_state.tournament = SwissTournament(new_players, st.session_state.num_rounds)
                    st.session_state.loaded_id = None
                    st.success("Tournament ready – scroll down to enter scores")
                    st.rerun()

    # --- Active tournament ---
    if not st.session_state.tournament:
        st.stop()

    tournament = st.session_state.tournament
    st.header(f"**{st.session_state.tournament_name}**")

    # --- Score keys ---
    score_keys = []
    for r in range(tournament.num_rounds):
        for m, match in enumerate(tournament.get_round_pairings(r)):
            if match and match.player2:
                k1 = f"hoops1_r{r}_m{m}"
                k2 = f"hoops2_r{r}_m{m}"
                v1, v2 = match.get_scores()
                if f"{k1}_val" not in st.session_state: st.session_state[f"{k1}_val"] = v1
                if f"{k2}_val" not in st.session_state: st.session_state[f"{k2}_val"] = v2
                score_keys.append((r, m, k1, k2))

    # --- Render rounds ---
    for r in range(tournament.num_rounds):
        pairings = tournament.get_round_pairings(r)
        real_matches = [m for m in pairings if m and m.player2]
        complete = all(sum(m.get_scores()) > 0 for m in real_matches)
        label = f"Round {r+1} ({len(real_matches)} matches)"
        with st.expander(label, expanded=(not complete)):
            c1, c2 = st.columns(2)
            display_idx = 1
            for match in real_matches:
                entry = next(e for e in score_keys if e[0] == r and pairings.index(match) == e[1])
                _, _, k1, k2 = entry
                col = c1 if display_idx % 2 else c2
                with col:
                    n, p1, h1, h2, p2, stat = st.columns([0.5, 2, 1, 1, 2, 1.5])
                    with n: st.markdown(f"**{display_idx}:**")
                    with p1: st.markdown(f"**{match.player1.name}**")
                    with h1: live1 = number_input_simple(k1, disabled=locked)
                    with h2: live2 = number_input_simple(k2, disabled=locked)
                    with p2: st.markdown(f"**{match.player2.name}**")
                    with stat:
                        if live1 == live2 == 0:
                            st.metric("Score", "–")
                        else:
                            st.metric("Score", f"{live1}-{live2}",
                                      delta=("P1" if live1 > live2 else "P2" if live2 > live1 else "Draw"))
                    st.markdown("---")
                    display_idx += 1
        if complete:
            st.success("**All games in this round recorded**")

    # --- Recalculate ---
    with st.form("recalc_form"):
        st.markdown("---")
        recalc = st.form_submit_button("Recalculate Standings", disabled=locked)
        st.markdown("---")
        if recalc:
            for p in tournament.players:
                p.points = p.wins = p.hoops_scored = p.hoops_conceded = 0
            for r, m_idx, k1, k2 in score_keys:
                match = tournament.get_round_pairings(r)[m_idx]
                if not match or not match.player2: continue
                h1 = st.session_state.get(f"{k1}_val", 0)
                h2 = st.session_state.get(f"{k2}_val", 0)
                if h1 == h2 and h1 > 0:
                    st.toast(f"Round {r+1} Match {m_idx+1}: draw – no points", icon="info")
                match.result = None
                match.set_result(h1, h2)
            st.success("Standings updated")
            st.rerun()

    # --- Standings ---
    st.subheader("Current Standings")
    standings = tournament.get_standings()
    df = pd.DataFrame([{
        "Rank": i+1, "Name": p.name, "Wins": p.wins, "Points": p.points,
        "Net": p.hoops_scored - p.hoops_conceded, "Scored": p.hoops_scored
    } for i, p in enumerate(standings)])
    st.dataframe(df, use_container_width=True)

    # --- Save / Export ---
    st.subheader("Save & Export")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Save Tournament", disabled=locked):
            tid = save_to_db(tournament, st.session_state.tournament_name)
            if tid:
                st.session_state.loaded_id = tid
                st.success("Saved")
                st.rerun()
    with c2:
        if st.button("CSV"):
            f = export_to_csv(tournament, st.session_state.tournament_name)
            if f:
                with open(f, "rb") as fp:
                    st.download_button("Download CSV", fp, f, mime="text/csv")
                os.remove(f)
    with c3:
        if st.button("Excel"):
            f = export_to_excel(tournament, st.session_state.tournament_name)
            if f:
                with open(f, "rb") as fp:
                    st.download_button("Download Excel", fp, f,
                                      mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                os.remove(f)

# --------------------------------------------------------------------------- #
# Export helpers
# --------------------------------------------------------------------------- #
def export_to_csv(tournament, name):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"{name}_{ts}.csv"
        with open(fn, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Round", "Match", "P1", "P2", "H1", "H2"])
            for r, rnd in enumerate(tournament.rounds):
                for m, match in enumerate(rnd):
                    if not match: continue
                    p2 = match.player2.name if match.player2 else "BYE"
                    h1, h2 = match.get_scores()
                    w.writerow([r+1, m+1, match.player1.name, p2, h1, h2])
        return fn
    except Exception as e:
        logger.error(f"CSV error: {e}")
        st.error(f"CSV error: {e}")
        return None

def export_to_excel(tournament, name):
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"{name}_{ts}.xlsx"
        rows = []
        for r, rnd in enumerate(tournament.rounds):
            for m, match in enumerate(rnd):
                if not match: continue
                p2 = match.player2.name if match.player2 else "BYE"
                h1, h2 = match.get_scores()
                rows.append({"Round": r+1, "Match": m+1, "Player 1": match.player1.name,
                             "Player 2": p2, "Hoops 1": h1, "Hoops 2": h2})
        pd.DataFrame(rows).to_excel(fn, index=False)
        return fn
    except Exception as e:
        logger.error(f"Excel error: {e}")
        st.error(f"Excel error: {e}")
        return None

if __name__ == "__main__":
    main()