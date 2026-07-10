"""Theme category (domain) engine — single source of truth.

"Turn how you think into a personal Python syntax layer": whatever the user
writes, the system first classifies the text into a THEME CATEGORY, then
maps each Python concept family (condition/iteration/function/output/data/
oop/error) to short, meaningful, English, theme-bound motifs drawn from that
category's table below.

Resolution cascade (most-specific wins):
  1. curated known themes   (CS2, GTA, Witcher, ... — generator.py tables)
  2. category detection     (this module: detect_domain)
  3. generic personal fallback

Both the deterministic token engine (``generator.py``) and the LLM-failure
profile fallback (``taxonomy_generator.py``) import these tables, so a
category added here immediately strengthens BOTH paths.

Motif style rules (quality gate depends on these):
  - 2 words max, English, identifier-safe after slugging
  - concrete and evocative: something a fan/practitioner would actually say
  - families must FEEL related to their Python role:
      condition -> a check/decision made in that world
      iteration -> a route/cycle/patrol repeated in that world
      function  -> a plan/recipe/ability that produces a result
      output    -> a message/call/broadcast
      data      -> a record/inventory/archive
      oop       -> a blueprint/type/lineage
      error     -> a failure/risk/rescue moment
"""

from __future__ import annotations

import re
import unicodedata

#: canonical Python concept families every motif table must cover
CONCEPT_FAMILIES: tuple[str, ...] = (
    "condition",
    "iteration",
    "function",
    "output",
    "data",
    "oop",
    "error",
)

DOMAIN_LABELS: dict[str, str] = {
    # --- long-standing specific domains ---
    "music": "Music",
    "cooking": "Cooking",
    "football": "Football",
    "space": "Space Exploration",
    "robotics": "Robotics",
    "aviation": "Aviation",
    "architecture": "Architecture",
    "medicine": "Medicine",
    "finance": "Finance",
    "mythology": "Mythology",
    # --- broad categories (plan: games/movies/anime/sports/professions/
    #     engineering/science/fantasy/daily life) ---
    "games": "Video Games",
    "movies_series": "Movies & Series",
    "anime": "Anime",
    "sports": "Sports",
    "professions": "Professions & Work",
    "engineering": "Engineering",
    "science": "Science",
    "fantasy": "Fantasy Worlds",
    "daily_life": "Daily Life",
}

#: ordered keyword checks — FIRST match wins, so specific domains must stay
#: above the broad categories that would also match them (football before
#: sports, space/robotics/aviation before science/engineering, mythology
#: before fantasy).
DOMAIN_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("music", ("music", "guitar", "piano", "song", "producer", "singer", "band", "dj", "spotify")),
    ("cooking", ("cooking", "cook", "baking", "baker", "chef", "kitchen", "recipe", "yemek", "mutfak")),
    ("football", ("football", "soccer", "striker", "goalkeeper", "premier league", "futbol", "mac izle")),
    ("space", ("space", "astronomy", "planet", "galaxy", "nasa", "black hole", "uzay", "gezegen", "astronot")),
    ("robotics", ("robot", "robotics", "drone", "mechatronic", "automation")),
    ("aviation", ("aviation", "airplane", "aircraft", "pilot", "flight", "ucak", "havacilik")),
    ("architecture", ("architecture", "architect", "building design", "blueprint", "city design", "mimar")),
    ("medicine", ("medicine", "medical", "doctor", "hospital", "clinic", "nurse", "doktor", "hastane", "tip fakultesi")),
    ("finance", ("finance", "trading", "stock", "investing", "crypto", "banking", "borsa", "yatirim")),
    ("mythology", ("mythology", "myth", "greek gods", "zeus", "olympus", "norse", "mitoloji")),
    # broad categories AFTER the specific ones
    ("anime", ("anime", "manga", "shonen", "naruto", "one piece", "attack on titan", "jujutsu", "dragon ball")),
    ("games", ("video game", "gamer", "gaming", "oyun oyn", "bilgisayar oyun", "playstation", "xbox", "steam", "esports", "e-spor", "fps", "rpg", "moba")),
    ("movies_series", ("movie", "film", "cinema", "series", "tv show", "netflix", "dizi", "sinema", "director", "yonetmen")),
    ("sports", ("sport", "basketball", "tennis", "volleyball", "swimming", "running", "gym", "fitness", "workout", "spor", "basketbol", "antrenman")),
    ("engineering", ("engineer", "engineering", "mechanical", "electrical", "civil engineer", "muhendis")),
    ("science", ("science", "physics", "chemistry", "biology lab", "experiment", "researcher", "bilim", "fizik", "kimya", "deney")),
    ("fantasy", ("fantasy", "dragon", "elf", "dungeon", "kingdom", "medieval", "sword", "ejderha", "krallik", "sovalye")),
    ("professions", ("lawyer", "teacher", "accountant", "psychologist", "journalist", "avukat", "ogretmen", "psikolog", "meslek", "my job", "isim geregi")),
    ("daily_life", ("daily life", "everyday", "morning routine", "coffee", "commute", "shopping", "gunluk hayat", "kahve", "rutin")),
)

DOMAIN_FAMILY_MOTIFS: dict[str, dict[str, tuple[str, ...]]] = {
    # ------------------------------------------------ specific domains
    "music": {
        "condition": ("sound check", "key change", "tempo check"),
        "iteration": ("beat loop", "chorus cycle", "next bar"),
        "function": ("song hook", "riff pattern", "final chord"),
        "output": ("stage shout", "studio monitor", "lyrics line"),
        "data": ("track list", "mix board", "sample crate"),
        "oop": ("band lineup", "instrument type", "arrangement blueprint"),
        "error": ("wrong note", "broken string", "lost take"),
    },
    "cooking": {
        "condition": ("taste check", "heat level", "recipe choice"),
        "iteration": ("stir cycle", "prep line", "next step"),
        "function": ("recipe method", "dish result", "prep plan"),
        "output": ("order call", "serving note", "kitchen bell"),
        "data": ("pantry shelf", "ingredient list", "recipe card"),
        "oop": ("dish blueprint", "chef role", "menu type"),
        "error": ("burnt pan", "missing spice", "failed bake"),
    },
    "football": {
        "condition": ("goal check", "offside flag", "match state"),
        "iteration": ("wing run", "passing lane", "next play"),
        "function": ("set_piece", "match_result", "training_drill"),
        "output": ("team_shout", "coach_call", "scoreboard"),
        "data": ("squad_sheet", "tactics_board", "stats_card"),
        "oop": ("player_role", "team_shape", "club_lineage"),
        "error": ("missed_pass", "foul_call", "injury_time"),
    },
    "space": {
        "condition": ("orbit_check", "gravity_shift", "mission_state"),
        "iteration": ("orbit_path", "star_route", "next_planet"),
        "function": ("launch_plan", "mission_result", "probe_task"),
        "output": ("signal_beam", "radio_ping", "mission_log"),
        "data": ("star_chart", "data_probe", "planet_record"),
        "oop": ("ship_blueprint", "planet_type", "fleet_lineage"),
        "error": ("signal_loss", "hull_breach", "failed_launch"),
    },
    "robotics": {
        "condition": ("sensor_check", "logic_gate", "safety_state"),
        "iteration": ("servo_cycle", "patrol_path", "next_joint"),
        "function": ("control_routine", "task_result", "motion_plan"),
        "output": ("status_beep", "debug_signal", "operator_prompt"),
        "data": ("sensor_map", "command_queue", "parts_bin"),
        "oop": ("robot_blueprint", "module_type", "bot_lineage"),
        "error": ("fault_code", "jammed_motor", "power_drop"),
    },
    "aviation": {
        "condition": ("preflight_check", "weather_window", "runway_state"),
        "iteration": ("flight_path", "holding_pattern", "next_waypoint"),
        "function": ("flight_plan", "landing_result", "checklist_step"),
        "output": ("tower_call", "cockpit_note", "radio_clearance"),
        "data": ("flight_log", "instrument_panel", "cargo_manifest"),
        "oop": ("airframe_blueprint", "aircraft_type", "fleet_lineage"),
        "error": ("stall_warning", "engine_fault", "missed_approach"),
    },
    "architecture": {
        "condition": ("site_check", "zoning_rule", "load_check"),
        "iteration": ("floor_plan", "stair_route", "next_room"),
        "function": ("design_method", "build_result", "draft_plan"),
        "output": ("client_note", "site_report", "render_view"),
        "data": ("material_list", "blueprint_index", "room_schedule"),
        "oop": ("building_blueprint", "room_type", "style_lineage"),
        "error": ("code_violation", "cracked_beam", "missing_permit"),
    },
    "medicine": {
        "condition": ("diagnosis_check", "symptom_shift", "triage_state"),
        "iteration": ("rounds_route", "care_cycle", "next_patient"),
        "function": ("treatment_plan", "recovery_result", "dose_method"),
        "output": ("patient_note", "chart_update", "lab_report"),
        "data": ("medical_chart", "case_record", "dose_list"),
        "oop": ("case_blueprint", "cell_type", "family_history"),
        "error": ("alert_code", "missed_dose", "test_failure"),
    },
    "finance": {
        "condition": ("risk_check", "market_shift", "entry_signal"),
        "iteration": ("trade_cycle", "price_route", "next_candle"),
        "function": ("strategy_rule", "profit_result", "order_plan"),
        "output": ("market_alert", "trade_note", "report_line"),
        "data": ("portfolio_book", "ledger_map", "watchlist"),
        "oop": ("asset_type", "fund_blueprint", "sector_lineage"),
        "error": ("stop_loss", "bad_fill", "margin_call"),
    },
    "mythology": {
        "condition": ("oracle_check", "fate_shift", "omen_state"),
        "iteration": ("hero_path", "quest_cycle", "next_trial"),
        "function": ("spell_rite", "quest_reward", "hero_task"),
        "output": ("bard_song", "oracle_message", "legend_note"),
        "data": ("relic_vault", "hero_scroll", "guild_record"),
        "oop": ("deity_lineage", "creature_type", "realm_blueprint"),
        "error": ("cursed_relic", "broken_oath", "failed_quest"),
    },
    # ------------------------------------------------ broad categories
    "games": {
        "condition": ("spawn_check", "boss_phase", "combo_window"),
        "iteration": ("quest_route", "respawn_cycle", "next_level"),
        "function": ("skill_combo", "loot_drop", "quest_strategy"),
        "output": ("chat_ping", "kill_feed", "score_popup"),
        "data": ("inventory_grid", "save_slot", "skill_tree"),
        "oop": ("character_build", "class_type", "guild_lineage"),
        "error": ("wipe_screen", "lag_spike", "failed_run"),
    },
    "movies_series": {
        "condition": ("plot_twist", "scene_cut", "casting_call"),
        "iteration": ("episode_arc", "season_run", "next_scene"),
        "function": ("script_beat", "director_cut", "shot_plan"),
        "output": ("trailer_drop", "credits_roll", "press_line"),
        "data": ("plot_archive", "scene_index", "cast_sheet"),
        "oop": ("character_arc", "genre_type", "franchise_lineage"),
        "error": ("plot_hole", "blooper_take", "cancelled_season"),
    },
    "anime": {
        "condition": ("power_check", "flashback_gate", "rival_signal"),
        "iteration": ("training_arc", "episode_loop", "next_saga"),
        "function": ("signature_move", "power_up", "battle_plan"),
        "output": ("battle_cry", "narrator_line", "intro_song"),
        "data": ("bounty_board", "jutsu_scroll", "crew_roster"),
        "oop": ("hero_archetype", "clan_lineage", "form_evolution"),
        "error": ("filler_trap", "power_drain", "lost_duel"),
    },
    "sports": {
        "condition": ("score_check", "foul_signal", "clock_state"),
        "iteration": ("training_lap", "drill_cycle", "next_set"),
        "function": ("play_call", "match_point", "workout_plan"),
        "output": ("whistle_blow", "coach_shout", "scoreboard_flash"),
        "data": ("stat_sheet", "league_table", "roster_card"),
        "oop": ("team_formation", "athlete_role", "club_lineage"),
        "error": ("missed_shot", "timeout_call", "injury_break"),
    },
    "professions": {
        "condition": ("deadline_check", "client_signal", "case_review"),
        "iteration": ("daily_rounds", "task_cycle", "next_meeting"),
        "function": ("work_plan", "case_result", "project_brief"),
        "output": ("status_report", "client_memo", "team_brief"),
        "data": ("case_file", "client_ledger", "task_board"),
        "oop": ("role_profile", "department_type", "career_path"),
        "error": ("missed_deadline", "failed_audit", "lost_case"),
    },
    "engineering": {
        "condition": ("stress_test", "tolerance_check", "spec_gate"),
        "iteration": ("assembly_line", "test_cycle", "next_iteration"),
        "function": ("design_spec", "test_result", "build_plan"),
        "output": ("status_gauge", "test_report", "control_signal"),
        "data": ("parts_catalog", "measurement_log", "schematic_sheet"),
        "oop": ("machine_blueprint", "component_type", "model_series"),
        "error": ("component_fault", "tolerance_breach", "failed_test"),
    },
    "science": {
        "condition": ("hypothesis_check", "control_group", "signal_threshold"),
        "iteration": ("trial_run", "sample_sweep", "next_experiment"),
        "function": ("lab_method", "measured_result", "study_design"),
        "output": ("lab_note", "journal_entry", "conference_talk"),
        "data": ("data_set", "sample_archive", "field_notebook"),
        "oop": ("specimen_type", "element_family", "theory_framework"),
        "error": ("failed_trial", "contaminated_sample", "outlier_alarm"),
    },
    "fantasy": {
        "condition": ("prophecy_check", "ward_gate", "moon_phase"),
        "iteration": ("quest_march", "patrol_round", "next_realm"),
        "function": ("spell_craft", "quest_reward", "battle_rite"),
        "output": ("herald_call", "raven_message", "tavern_tale"),
        "data": ("spell_tome", "royal_archive", "loot_chest"),
        "oop": ("house_banner", "creature_kind", "bloodline_seal"),
        "error": ("broken_curse", "failed_ritual", "dragon_wrath"),
    },
    "daily_life": {
        "condition": ("alarm_check", "weather_peek", "mood_meter"),
        "iteration": ("morning_routine", "errand_loop", "next_stop"),
        "function": ("day_plan", "checklist_done", "coffee_ritual"),
        "output": ("group_message", "sticky_note", "voice_memo"),
        "data": ("shopping_list", "photo_album", "calendar_page"),
        "oop": ("household_role", "routine_pattern", "family_tree"),
        "error": ("missed_bus", "spilled_coffee", "dead_battery"),
    },
}


def detect_domain(text: str) -> str | None:
    """Classify free text into a theme category key, or None.

    Matching is ASCII-folded and case-insensitive so Turkish input matches
    too ("uçak" -> aviation). Order = specificity: specific domains are
    listed before the broad categories that would also match them.
    """
    folded = _ascii_fold(text)
    for key, needles in DOMAIN_KEYWORDS:
        if any(needle in folded for needle in needles):
            return key
    return None


def domain_label(key: str) -> str:
    return DOMAIN_LABELS.get(key, key.replace("_", " ").title())


def domain_family_motifs(key: str) -> dict[str, tuple[str, ...]]:
    return DOMAIN_FAMILY_MOTIFS.get(key, {})


def _ascii_fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().casefold()
