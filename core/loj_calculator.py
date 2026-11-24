# core/loj_calculator.py
"""
Deterministic Lands of Jail upgrade cost calculators, hero directory,
SvS day-by-day lookup, and item/buff pricing engine.
Data sourced from Lands of Jail Unofficial Wiki (landsofjail.miraheze.org) & LOJ XLab (lojxlab.com).
"""
import re
from typing import Dict, List, Optional, Tuple

# ---------- 1. Exclusive Equipment / Weapons (Lv 0 -> 10) ----------
# Key = target level N (cost to upgrade from N-1 -> N)
EXCLUSIVE_EQUIP_PARTS: Dict[int, int] = {
    1: 10,
    2: 25,
    3: 25,
    4: 45,
    5: 45,
    6: 65,
    7: 65,
    8: 85,
    9: 85,
    10: 100,
}

EXCLUSIVE_SEASON_BONUS: Dict[int, Tuple[str, str, str]] = {
    1: ("+5.25%/lvl", "+52.5%", "270,000"),
    2: ("+6.3%/lvl", "+63%", "324,000"),
    3: ("+7.35%/lvl", "+73.5%", "378,000"),
    4: ("+9.7%/lvl", "+97%", "499,500"),
    5: ("+11.7%/lvl", "+117%", "599,400"),
    6: ("+14%/lvl", "+140%", "720,900"),
}

# ---------- 2. Equipment Reformation / Mastery Reformation (Lv 1 -> 20) ----------
# Key = target level N -> (Precision Gears, Magnets)
REFORMATION_COSTS: Dict[int, Tuple[int, int]] = {
    1: (20, 0),
    2: (40, 0),
    3: (60, 0),
    4: (80, 0),
    5: (100, 0),
    6: (120, 0),
    7: (140, 0),
    8: (160, 0),
    9: (180, 0),
    10: (200, 220),
    11: (220, 200),
    12: (240, 400),
    13: (260, 600),
    14: (280, 800),
    15: (300, 1000),
    16: (320, 1200),
    17: (360, 1400),
    18: (380, 1600),
    19: (400, 1800),
    20: (400, 2000),
}

# ---------- 3. Tome Upgrade Costs (Lv 0 -> 18) ----------
# Key = target level N (cost for N-1 -> N) -> (Wisdom, Knowledge, Mystery Tome, Bonus%)
TOME_COSTS: Dict[int, Tuple[int, int, int, str]] = {
    1: (10, 10, 0, "18.90%"),
    2: (50, 60, 0, "25.20%"),
    3: (90, 110, 0, "33.60%"),
    4: (160, 200, 0, "39.90%"),
    5: (270, 330, 0, "52.50%"),
    6: (380, 460, 0, "63.00%"),
    7: (480, 600, 0, "73.50%"),
    8: (540, 660, 0, "84.00%"),
    9: (620, 780, 0, "94.50%"),
    10: (760, 920, 0, "105.00%"),
    11: (920, 1040, 0, "115.50%"),
    12: (1040, 1240, 0, "126.00%"),
    13: (1040, 1240, 8, "146.00%"),
    14: (1080, 1300, 15, "166.00%"),
    15: (1080, 1300, 22, "186.00%"),
    16: (1120, 1400, 35, "206.00%"),
    17: (1120, 1400, 50, "226.00%"),
    18: (1180, 1540, 66, "250.00%"),
}

# ---------- 4. Warden's Office (Lv 2 -> 30) ----------
# Key = target level -> (required_buildings, cost, time, unlocks, offline_cap, power)
OFFICE_LEVELS: Dict[int, Tuple[str, str, str, str, str, str]] = {
    2: ("Kitchen Lv.1", "350 W", "6 sec", "Shower Room 1, Cell 4, Playground", "1m", "4,560"),
    3: ("Cell 1 Lv.2", "1,600 W", "1 min", "Factory, Cell 5", "1m", "7,800"),
    4: ("Factory Lv.3", "3,600 W, 700 S", "3 min", "Utility Room", "5m", "12,120"),
    5: ("Cell 3 Lv.3", "15,000 W, 3,000 S", "6 min", "Supply Center, Arrest, Laundry, Bag, Heroes", "10m", "18,600"),
    6: ("Supply Center Lv.1, Shower Room 1 Lv.5", "40K W, 8K S, 2K Gas", "30 min", "Cell 6, Shop, Events, Rise to Power, 7-Day Check-in", "15m", "28,320"),
    7: ("Playground Lv.5", "140K W, 28K S, 2K Gas", "1 hr", "Cell 7, Shieldbearer Barracks, Scout Hangar, Daily Tasks", "30m", "42,360"),
    8: ("Shieldbearer Barracks Lv.7", "240K W, 48K S, 12K Gas", "2h 30m", "Cell 8, Comms Center, Shooter Barracks, Medical Station, Arena", "1h", "56,400"),
    9: ("Comms Center Lv.8, Medical Station Lv.1", "500K W, 100K S, 25K Gas", "4h 30m", "Cell 9, Inventory, Bomber Barracks, Lab", "1h 15m", "70,440"),
    10: ("Shooter Barracks Lv.9, Lab Lv.1", "900K W, 180K S, 45K Gas", "6 hr", "Cell 10, Command Center, Fortune Arcade", "1h 30m", "90,840"),
    11: ("Comms Center Lv.10, Bomber Barracks Lv.10", "2.5M F, 2.5M W, 500K S, 125K Gas", "7h 30m", "Cell 11, Shower Room 2, Recruitment Hall", "1h 45m", "111,240"),
    12: ("Comms Center Lv.11, Command Center Lv.1", "3M F, 3M W, 600K S, 150K Gas", "9 hr", "Cell 12", "2h", "131,640"),
    13: ("Comms Center Lv.12, Shieldbearer Barracks Lv.12", "4.5M F, 4.5M W, 900K S, 225K Gas", "11 hr", "Cell 13", "2h 40m", "166,080"),
    14: ("Comms Center Lv.13, Shooter Barracks Lv.13", "6M F, 6M W, 1.2M S, 300K Gas", "14 hr", "Cell 14", "3h 20m", "200,520"),
    15: ("Comms Center Lv.14, Bomber Barracks Lv.14", "9M F, 9M W, 1.8M S, 450K Gas", "18 hr", "Cell 15, Arsenal", "4h", "234,960"),
    16: ("Comms Center Lv.15, Lab Lv.15", "12M F, 12M W, 2.4M S, 600K Gas", "1d 1h 24m", "Cell 16, Crystal Clash eligibility", "4h 20m", "283,440"),
    17: ("Comms Center Lv.16, Shieldbearer Barracks Lv.16", "18M F, 18M W, 3.6M S, 900K Gas", "1d 12h 34m", "Cell 17", "4h 40m", "331,920"),
    18: ("Comms Center Lv.17, Shooter Barracks Lv.17", "25M F, 25M W, 5M S, 1.2M Gas", "1d 19h 53m", "Cell 18", "5h", "380,400"),
    19: ("Comms Center Lv.18, Bomber Barracks Lv.18", "30M F, 30M W, 6M S, 1.5M Gas", "2d 17h 50m", "Cell 19, Haven Island", "5h 20m", "449,280"),
    20: ("Comms Center Lv.19, Lab Lv.19", "40M F, 40M W, 8M S, 2M Gas", "3d 10h 18m", "Cell 20", "5h 40m", "518,160"),
    21: ("Comms Center Lv.20, Shieldbearer Barracks Lv.20", "50M F, 50M W, 10M S, 2.5M Gas", "4d 10h 59m", "Higher capacity & power", "6h", "587,040"),
    22: ("Comms Center Lv.21, Shooter Barracks Lv.21", "70M F, 70M W, 14M S, 3.5M Gas", "6d 16h 29m", "Higher capacity & power", "6h 20m", "690,360"),
    23: ("Comms Center Lv.22, Bomber Barracks Lv.22", "90M F, 90M W, 18M S, 4.5M Gas", "9d 8h 40m", "Higher capacity & power", "6h 40m", "793,680"),
    24: ("Comms Center Lv.23, Lab Lv.23", "120M F, 120M W, 24M S, 6M Gas", "13d 2h 33m", "Prisoner Lv.8", "7h", "897,000"),
    25: ("Comms Center Lv.24", "160M F, 160M W, 32M S, 8M Gas", "18d 8h 22m", "Higher capacity & power", "8h 40m", "1,000,320"),
    26: ("Comms Center Lv.25, Shooter Barracks Lv.25", "210M F, 210M W, 40M S, 10.5M Gas", "21d 2h 26m", "Higher capacity & power", "10h 20m", "1,152,120"),
    27: ("Comms Center Lv.26, Bomber Barracks Lv.26", "300M F, 300M W, 60M S, 15M Gas", "25d 7h 43m", "Prisoner Lv.9, Max 12h Offline Cap", "12h", "1,303,920"),
    28: ("Comms Center Lv.27, Lab Lv.27", "350M F, 350M W, 70M S, 17.5M Gas", "29d 2h 52m", "Pure Power", "12h", "1,455,720"),
    29: ("Comms Center Lv.28, Shieldbearer Barracks Lv.28", "450M F, 450M W, 90M S, 22.5M Gas", "33d 11h 42m", "Pure Power", "12h", "1,607,520"),
    30: ("Comms Center Lv.29, Shooter Barracks Lv.29", "600M F, 600M W, 120M S, 30M Gas", "40d 4h 22m", "Unlocks Forticlad progression", "12h", "1,828,200"),
}

# ---------- 5. Forticlad Levels (FC 1 -> FC 10) ----------
# Key = FC level N -> (required_buildings, office_fc_per_stage, office_afc_per_stage, total_fc_all_buildings, total_afc_all_buildings)
FORTICLAD_LEVELS: Dict[int, Tuple[str, int, int, int, int]] = {
    1: ("Comms Center Lv.29, Shooter Barracks Lv.29", 250, 0, 3950, 0),
    2: ("Comms Center FC 1, Bomber Barracks FC 1", 320, 0, 4750, 0),
    3: ("Shieldbearer Barracks FC 2, Comms Center FC 2", 490, 0, 7100, 0),
    4: ("Shooter Barracks FC 3, Comms Center FC 3", 600, 0, 8400, 0),
    5: ("Bomber Barracks FC 4, Comms Center FC 4", 720, 0, 10050, 0),
    6: ("Shieldbearer Barracks FC 5, Comms Center FC 5", 360, 24, 5350, 345),
    7: ("Shooter Barracks FC 6, Comms Center FC 6", 400, 36, 6000, 525),
    8: ("Bomber Barracks FC 7, Comms Center FC 7", 460, 48, 6900, 750),
    9: ("Comms Center FC 8, Barracks FC 8", 510, 72, 7150, 995),
    10: ("Comms Center FC 9, Barracks FC 9", 630, 168, 8950, 2340),
}

# ---------- 6. Hero Directory (Seasons 1-7, Class, Role, Notes) ----------
# key = lowercase hero name -> (Display Name, Class, Gen/Season, Summary)
HERO_DIRECTORY: Dict[str, Tuple[str, str, str, str]] = {
    "tyronn": ("Tyronn", "Shieldbearer", "Gen 1 (SSR)", "**S-Tier Rally Leader & Joiner.** #1 overall rally leader once exclusive gear (**Brutal Gauntlets**, +73.5% / 378k power at Lv.10 — S3-level exception!) is built. Core of S1–S5 rally teams."),
    "tyron": ("Tyronn", "Shieldbearer", "Gen 1 (SSR)", "**S-Tier Rally Leader & Joiner.** #1 overall rally leader once exclusive gear (**Brutal Gauntlets**, +73.5% / 378k power at Lv.10) is built. Core of S1–S5 rally teams."),
    "phoenix": ("Phoenix", "Shieldbearer", "Gen 1 (SSR)", "**S-Tier Rally Joiner & S-Tier Solo Attack**, A-Tier Rally Leader (often beats Tyronn before Tyronn's exclusive gear is built). Exclusive gear: **Colossus Hammer** (+65.63% / 337.5k at Lv.10)."),
    "vivian": ("Vivian", "Bomber", "Gen 1 (SSR)", "**S-Tier Utility (+15% Building Speed, −15% Building Cost)** & A-Tier Rally Joiner. Also used in S1–S2 rally lineups."),
    "inata": ("Inata", "Shooter", "Gen 1 (SSR)", "**S-Tier Utility (+15% Research Speed)** & S2–S3 Garrison Defense Shooter. Avoid as rally leader/joiner (D-Tier in rallies)."),
    "devilian": ("Devilian", "Shooter", "Gen 1 (SSR)", "**S-Tier Utility (+30% Troop Training Speed)**, S1 Rally Shooter, B-Tier Rally Joiner."),
    "alph": ("Alph", "Bomber", "Gen 2 (SSR)", "S3 Solo Attack Bomber & strong in SvS/PvP player rallies where Lethality/DEF skills apply. Avoid as Trial Cage joiner."),
    "mireya": ("Mireya", "Shooter", "Gen 2 (SSR)", "S2 Rally Shooter & B-Tier Rally Leader; stronger in SvS/Supreme Prison rallies than Trial Cage."),
    "caesar": ("Caesar", "Shieldbearer", "Gen 2 (SSR)", "S2 Garrison Defense Shieldbearer. Avoid as rally leader (D-Tier)."),
    "lanchester": ("Lanchester", "Bomber", "Gen 2 (SSR)", "**S-Tier Garrison Defense Bomber (S2–S4)** & S-Tier Arrests hero."),
    "veronica": ("Veronica", "Shooter", "Gen 3 (SSR)", "**S-Tier Rally Joiner**, S3–S4 Solo Attack Shooter, and S-Tier Arrests hero."),
    "whisper": ("Whisper", "Bomber", "Gen 3 (SSR)", "**S-Tier Rally Joiner (#1 on LOJ XLab: guaranteed −20% enemy DEF)**, S3 Rally Bomber, and strong S5 test option with Tyronn + Ada."),
    "xuanming": ("Xuanming", "Shieldbearer", "Gen 3 (SSR)", "S3 Garrison Defense Shieldbearer & S-Tier Arrests hero."),
    "sawyer": ("Sawyer", "Shooter", "Gen 3 (SSR)", "**A-Tier Rally Leader (#1 leader on LOJ XLab for full-rally scaling)**, S3–S4 Rally Shooter, and S-Tier Arrests hero."),
    "zoltan": ("Zoltan", "Shieldbearer", "Gen 4 (SSR)", "**S4 Garrison Defense Shieldbearer** — holds up especially well against mixed damage."),
    "drake": ("Drake", "Shooter", "Gen 4 (SSR)", "**S4–S5 Garrison Defense Shooter** & B-Tier conditional Rally Joiner."),
    "koschevoi": ("Koschevoi", "Bomber", "Gen 4 (SSR)", "**S-Tier Rally Joiner**, S4–S5 Solo Attack Bomber, and B-Tier Rally Leader."),
    "ryuichi": ("Ryuichi Ito", "Bomber", "Gen 4 (SSR)", "**A-Tier Rally Leader & Joiner**, S4–S5 Rally Bomber. Beats Koschevoi once exclusive equipment is near max."),
    "ada": ("Ada", "Shooter", "Gen 5 (SSR)", "**S-Tier Rally Leader (top Shooter leader)** & S5 Rally Shooter. Use `1% Shieldbearers / 9% Bombers / 90% Shooters` when Ada leads Trial Cage."),
    "edwin": ("Edwin", "Shooter", "Gen 5 (SSR)", "S5 Solo Attack Shooter & B-Tier Rally Leader."),
    "lee": ("Lee", "Bomber", "Gen 5 (SSR)", "S5 Garrison Defense Bomber & B-Tier conditional joiner (needs tactical damage dealer)."),
    "marcus": ("Marcus", "Shieldbearer", "Gen 5 (SSR)", "**S5 Garrison Defense Shieldbearer** — strongest tank against heavy basic-attack damage. Exclusive gear: **Steel Arm** (+11.7%/lvl)."),
    "kate": ("Kate", "Shooter", "Gen 6 (SSR)", "A-Tier Rally Joiner, B-Tier Leader, & S6–S7 Defense hero. Exclusive gear: **Wild Idea** (+14%/lvl)."),
    "otto": ("Otto", "Shieldbearer", "Gen 6 (SSR)", "B-Tier Rally Leader & S6–S7 Defense hero. Exclusive gear: **Devouring Mask** (+14%/lvl)."),
    "worrell": ("Worrell", "Bomber", "Gen 6 (SSR)", "S6–S7 Solo Attack hero & B-Tier Rally Joiner (boosts basic attacks)."),
    "wukong": ("Wukong", "Bomber", "Gen 6 (SSR)", "**S-Tier Rally Leader (top Bomber leader)** & S6–S7 Rally meta. Exclusive gear: **Divine Power** (+140% / 720,900 power at Lv.10)."),
    "fran": ("Fran & Pike", "Shieldbearer", "Gen 7 (SSR)", "Newest Season 7 SSR Defense Shieldbearer."),
    "pike": ("Fran & Pike", "Shieldbearer", "Gen 7 (SSR)", "Newest Season 7 SSR Defense Shieldbearer."),
    "boogie": ("Boogie", "Bomber", "Gen 7 (SSR)", "Season 7 SSR Defense & B-Tier Rally Leader/Joiner (boosts basic attacks)."),
    "rin": ("Rin", "Shooter", "Gen 7 (SSR)", "Season 7 SSR **A-Tier Rally Leader** (second-choice Shooter leader after Ada)."),
    "rex": ("Rex", "Shooter", "Gen 7 (SSR)", "Season 7 SSR Solo Attack hero, A-Tier Utility (extra monster damage), & B-Tier Shooter-only Joiner."),
    "lunarl": ("Lunarl", "Bomber", "SR (Epic)", "**S-Tier Rally Joiner** — one of the easiest & strongest joiners to build! Uses Epic War Skill Books."),
    "minyeon": ("Minyeon & Taehun", "Bomber", "SR (Epic)", "**S-Tier Rally Joiner** & A-Tier Utility (extra damage vs monsters)."),
    "taehun": ("Minyeon & Taehun", "Bomber", "SR (Epic)", "**S-Tier Rally Joiner** & A-Tier Utility (extra damage vs monsters)."),
    "lofili": ("Lofili", "Shooter", "SR (Epic)", "**A-Tier Rally Joiner** (strong budget joiner before SSR joiners are built)."),
    "samir": ("Samir", "Bomber", "SR (Epic)", "**A-Tier Rally Joiner**."),
    "ekko": ("Ekko", "Bomber", "SR (Epic)", "B-Tier Joiner; much stronger in SvS / Supreme Prison player rallies than Trial Cage."),
    "mia": ("Mia", "Shooter", "SR (Epic)", "**S-Tier Utility (−20% stamina cost, +100% march speed vs field enemies)** & A-Tier Arrests. Has **no Exclusive Equipment**; avoid in war rallies (D-Tier)."),
    "durga": ("Durga", "Shieldbearer", "R (Rare)", "**A-Tier Utility (Factory profit & gathering).** Keep for gathering, never send to combat rallies."),
    "harton": ("Harton", "Shieldbearer", "R (Rare)", "**A-Tier Utility (Factory profit & gathering).** Uses Rare Skill Books; keep for gathering, not combat."),
    "pasino": ("Pasino", "Bomber", "R (Rare)", "**A-Tier Utility (Factory profit & gathering).** Keep for gathering, not combat."),
    "aiksen": ("Aiksen", "Shooter", "R (Rare)", "**A-Tier Utility (Factory profit & gathering).** Keep for gathering, not combat."),
}

GENERATION_HEROES: Dict[int, str] = {
    1: "**Gen 1:** Phoenix, Tyronn, Vivian, Inata, Devilian *(Gen 1 Parts Choice Chests are now only in the Flea Market event)*",
    2: "**Gen 2:** Alph, Mireya, Caesar, Lanchester",
    3: "**Gen 3:** Veronica, Whisper, Xuanming, Sawyer",
    4: "**Gen 4:** Zoltan, Drake, Koschevoi, Ryuichi Ito",
    5: "**Gen 5:** Ada, Edwin, Lee, Marcus",
    6: "**Gen 6:** Kate, Otto, Worrell, Wukong",
    7: "**Gen 7:** Fran & Pike, Boogie, Rin, Rex",
}

SVS_PREP_DAYS: Dict[int, Tuple[str, str]] = {
    1: (
        "⚔️ SvS Preparation — Day 1",
        "• **Forticlad Core:** 3,000 pts each\n"
        "• **1-min Speedup** (Construction / Research / Troop Training or Promotion): 90 pts each\n"
        "• **Tome Rating (+1):** 210 pts",
    ),
    2: (
        "⚔️ SvS Preparation — Day 2",
        "• **Forticlad Core:** 3,000 pts each\n"
        "• **1-min Speedup** (Construction / Research / Training): 90 pts each\n"
        "• **Reinforcement Spin:** 24,000 pts each\n"
        "• **Hero Shards:** Rare `1,050` | Epic `3,660` | Legendary `9,120` pts\n"
        "• **Gathering:** 1k Food / 1k Wood / 200 Steel / 50 Gasoline = `6 pts`",
    ),
    3: (
        "⚔️ SvS Preparation — Day 3",
        "• **Power Modules:** Standard `1,300` | Advanced `6,500` pts\n"
        "• **Module Chests:** Solo `1,250` | Formation `2,500` | Barrier `3,750` pts\n"
        "• **Tome Rating (+1):** 210 pts • **Reinforcement Spin:** 24,000 pts\n"
        "• **Hero Shards:** Rare `1,050` | Epic `3,660` | Legendary `9,120` pts\n"
        "• **Beast Rally:** `90,000` pts • **Fugitives:** Lv.1–10 `27k` up to Lv.26–30 `36k` pts",
    ),
    4: (
        "⚔️ SvS Preparation — Day 4",
        "• **Hero Exclusive Equipment Part:** `12,000` pts each\n"
        "• **Precision Gear:** `6,000` pts each\n"
        "• **Tome Rating (+1):** `210` pts\n"
        "• **Soldier Training:** Lv.1 `9` | Lv.5 `36` | Lv.7 `75` | Lv.8 `105` | Lv.9 `135` | Lv.10 `180` pts",
    ),
    5: (
        "⚔️ SvS Preparation — Day 5",
        "• **Hero Exclusive Equipment Part:** `12,000` pts each\n"
        "• **Precision Gear:** `6,000` pts each\n"
        "• **Forticlad Core:** `3,000` pts each\n"
        "• **Power Modules:** Standard `1,300` | Advanced `6,500` pts • **Module Chests:** `1,250 / 2,500 / 3,750` pts\n"
        "• **Tome Rating (+1):** `210` pts • **1-min Speedup (All):** `90` pts",
    ),
}


def _extract_level_range(q_low: str, min_lvl: int, max_lvl: int, allow_zero_start: bool = True) -> Optional[Tuple[int, int]]:
    """Parse 'lvl 5 to lvl 6', '5-6', 'from 5 to 10', 'level 6', 'fc5 to fc6', etc."""
    # Pattern 1: explicit range (e.g., "5 to 6", "lvl 5 to lvl 6", "5->6", "5-6", "fc 5 to fc 6")
    m = re.search(
        r"(?:lvl|level|lv|fc|forticlad|tome|ref|reformation|office|wo)?\s*\.?\s*(\d{1,2})\s*(?:to|->|→|-|~|till|until)\s*(?:lvl|level|lv|fc|forticlad|tome|ref|reformation|office|wo)?\s*\.?\s*(\d{1,2})",
        q_low,
    )
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if b < a:
            a, b = b, a
        lo = 0 if allow_zero_start else min_lvl
        if lo <= a <= max_lvl and min_lvl <= b <= max_lvl:
            return (a, b)

    # Pattern 2: single level mention (e.g., "lvl 6", "level 25", "fc 3", "office 28")
    m2 = re.search(r"(?:lvl|level|lv|fc|forticlad|tome|ref|reformation|office|wo)\s*\.?\s*(\d{1,2})\b", q_low)
    if m2:
        lvl = int(m2.group(1))
        if min_lvl <= lvl <= max_lvl:
            return (max(0, lvl - 1), lvl)

    return None


def answer_loj_structured_query(raw_query: str) -> Optional[Tuple[str, str]]:
    """
    Handles exact numeric Lands of Jail questions:
    - Exclusive Equipment / Weapon level costs (0-10)
    - Equipment Reformation level costs (1-20)
    - Tome upgrade costs (0-18)
    - Warden's Office (2-30) & Forticlad (1-10) requirements & costs
    - SvS Prep Day 1-5 exact points
    - Generation 1-7 hero lists & individual hero lookups
    - Buffs, Shields & Upgrade Materials pricing/sources
    """
    q = (raw_query or "").strip()
    q_low = q.lower()
    tokens = set(re.findall(r"[a-z0-9]+", q_low))

    # 1. Equipment Reformation / Mastery Reformation (Lv 1-20)
    if any(w in q_low for w in ("reformation", "reform", "mastery ref", "precision gear", "ref lvl", "ref level")):
        rng = _extract_level_range(q_low, 1, 20, allow_zero_start=True)
        if rng:
            start, end = rng
            if start == end:
                start = max(0, end - 1)
            gears = sum(REFORMATION_COSTS[lvl][0] for lvl in range(start + 1, end + 1))
            magnets = sum(REFORMATION_COSTS[lvl][1] for lvl in range(start + 1, end + 1))
            svs_pts = gears * 6000
            step_label = f"Lv.{start} → Lv.{end}"
            lines = [
                f"• **Precision Gear Needed:** **`{gears:,}`**",
                f"• **Magnets Needed:** **`{magnets:,}`**" + (" *(Magnets start at Lv.10)*" if magnets == 0 else ""),
                f"• **SvS Day 4/5 Points (from Gears):** **`{svs_pts:,}` pts** (`6,000` pts/gear)",
            ]
            if end - start <= 5:
                breakdown = ", ".join(
                    f"Lv.{l}: {REFORMATION_COSTS[l][0]}G" + (f"+{REFORMATION_COSTS[l][1]:,}M" if REFORMATION_COSTS[l][1] else "")
                    for l in range(start + 1, end + 1)
                )
                lines.append(f"• **Step Breakdown:** `{breakdown}`")
            lines.append("• **Full 1 → 20 Total:** `4,260 Precision Gear` + `11,220 Magnets`")
            return (f"🔧 Equipment Reformation Cost ({step_label})", "\n".join(lines))

    # 2. Hero Exclusive Equipment / Weapons (Lv 0-10)
    is_excl = (
        any(w in q_low for w in ("exclusive", "weapon", "parts needed", "hero equip", "hero euip", "hero gear", "equipment needed", "euipment needed"))
        and not any(w in q_low for w in ("reformation", "reform", "forticlad", "tome", "office"))
    )
    if is_excl:
        rng = _extract_level_range(q_low, 1, 10, allow_zero_start=True)
        if rng:
            start, end = rng
            if start == end:
                start = max(0, end - 1)
            parts = sum(EXCLUSIVE_EQUIP_PARTS[lvl] for lvl in range(start + 1, end + 1))
            svs_pts = parts * 12000
            running_total = sum(EXCLUSIVE_EQUIP_PARTS[lvl] for lvl in range(1, end + 1))
            remaining = 550 - running_total
            lines = [
                f"• **Exclusive Equipment Parts Needed:** **`{parts:,}` parts**",
                f"• **SvS Day 4/5 Points:** **`{svs_pts:,}` pts** (`12,000` pts/part)",
                f"• **Cumulative (0 → {end}):** `{running_total:,}` / `550` parts (`{remaining:,}` remaining to max Lv.10)",
                "• **Skill Rhythm:** Odd levels upgrade **Arrest** skill • Even levels upgrade **War** skill",
            ]
            if end - start <= 5:
                breakdown = ", ".join(f"{l-1}→{l}: {EXCLUSIVE_EQUIP_PARTS[l]}" for l in range(start + 1, end + 1))
                lines.append(f"• **Step Breakdown:** `{breakdown}` *(costs step up in pairs: 25, 45, 65, 85, 100)*")
            return (f"🗡️ Hero Exclusive Equipment Cost (Lv.{start} → Lv.{end})", "\n".join(lines))

    # 3. Tome Upgrade Costs (Lv 0-18)
    if "tome" in tokens or "tomes" in tokens or "mystery tome" in q_low or "seal of wisdom" in q_low:
        rng = _extract_level_range(q_low, 1, 18, allow_zero_start=True)
        if rng:
            start, end = rng
            if start == end:
                start = max(0, end - 1)
            wisdom = sum(TOME_COSTS[l][0] for l in range(start + 1, end + 1))
            know = sum(TOME_COSTS[l][1] for l in range(start + 1, end + 1))
            mystery = sum(TOME_COSTS[l][2] for l in range(start + 1, end + 1))
            bonus = TOME_COSTS[end][3]
            lines = [
                f"• **Seal of Wisdom:** **`{wisdom:,}`** *(1 tome)* | **`{wisdom * 6:,}`** *(full 6-tome troop set)*",
                f"• **Seal of Knowledge:** **`{know:,}`** *(1 tome)* | **`{know * 6:,}`** *(full 6-tome set)*",
                f"• **Seal of Mystery Tome:** **`{mystery:,}`** *(1 tome; starts at Lv.12 → 13)*",
                f"• **Bonus Stat at Lv.{end}:** **`{bonus}`** *(Max Lv.18 = 250.00%)*",
            ]
            return (f"📖 Tome Upgrade Cost (Lv.{start} → Lv.{end})", "\n".join(lines))

    # 4. Forticlad Upgrade Costs (FC 1-10)
    if any(w in q_low for w in ("forticlad", "fc ", "fc1", "fc2", "fc3", "fc4", "fc5", "fc6", "fc7", "fc8", "fc9", "fc10")):
        rng = _extract_level_range(q_low, 1, 10, allow_zero_start=True)
        if rng:
            start, end = rng
            if start == end:
                start = max(0, end - 1)
            tot_fc = sum(FORTICLAD_LEVELS[l][3] for l in range(start + 1, end + 1))
            tot_afc = sum(FORTICLAD_LEVELS[l][4] for l in range(start + 1, end + 1))
            office_fc = sum(FORTICLAD_LEVELS[l][1] * 5 for l in range(start + 1, end + 1))
            office_afc = sum(FORTICLAD_LEVELS[l][2] * 5 for l in range(start + 1, end + 1))
            req = FORTICLAD_LEVELS[end][0]
            svs_pts = tot_fc * 3000
            from_lbl = "Office 30" if start == 0 else f"FC {start}"
            lines = [
                f"• **Warden's Office Only (5 stages/lvl):** **`{office_fc:,} FC`**" + (f" + **`{office_afc:,} AFC`**" if office_afc else ""),
                f"• **All Main Buildings Combined:** **`{tot_fc:,} FC`**" + (f" + **`{tot_afc:,} AFC`**" if tot_afc else ""),
                f"• **Prerequisites for FC {end}:** {req}",
                f"• **SvS Day 1/2/5 Points (All Buildings):** **`{svs_pts:,}` pts** (`3,000` pts/FC Core)",
            ]
            return (f"🏰 Forticlad Upgrade Cost ({from_lbl} → FC {end})", "\n".join(lines))

    # 5. Warden's Office Level Requirements (Lv 2-30)
    if any(w in q_low for w in ("warden office", "warden's office", "office lvl", "office level", "office lv", "wo ", "city hall", "hq ")):
        rng = _extract_level_range(q_low, 2, 30, allow_zero_start=False)
        if rng:
            start, end = rng
            if end - start == 1 or start == end:
                req, cost, btime, unlocks, off_cap, pwr = OFFICE_LEVELS[end]
                return (
                    f"🏛️ Warden's Office — Level {end}",
                    f"• **Required Buildings:** {req}\n"
                    f"• **Resources:** `{cost}`\n"
                    f"• **Base Build Time:** `{btime}`\n"
                    f"• **Unlocks:** {unlocks}\n"
                    f"• **Offline Cap:** `{off_cap}` • **Building Power:** `{pwr}`",
                )
            # Multi-level summary (e.g., Office 25 to 30)
            rows = []
            for lvl in range(start + 1, end + 1):
                req, cost, btime, _, _, _ = OFFICE_LEVELS[lvl]
                rows.append(f"• **Lv.{lvl}:** {req} | `{cost}` | `{btime}`")
            return (
                f"🏛️ Warden's Office Roadmap (Lv.{start} → Lv.{end})",
                "\n".join(rows[:10]) + ("\n*(Ask a smaller range or single level for full details.)*" if len(rows) > 10 else ""),
            )

    # 6. SvS Preparation Phase Day 1-5 specific lookup
    if any(w in tokens for w in ("svs", "supreme", "prep", "preparation")):
        m_day = re.search(r"\b(?:day|d)\s*([1-5])\b", q_low)
        if m_day:
            d = int(m_day.group(1))
            return SVS_PREP_DAYS[d]

    # 7. Generation 1-7 Hero List lookup
    if any(w in q_low for w in ("gen ", "gen1", "gen2", "gen3", "gen4", "gen5", "gen6", "gen7", "generation", "parts choice chest")):
        m_gen = re.search(r"\b(?:gen|generation|s|season)\s*([1-7])\b", q_low)
        if m_gen:
            g = int(m_gen.group(1))
            extra = ""
            if g in EXCLUSIVE_SEASON_BONUS:
                per_l, at_10, pwr_10 = EXCLUSIVE_SEASON_BONUS[g]
                extra = f"\n• **Exclusive Equipment Bonus:** `{per_l}` (`{at_10}` & `{pwr_10}` power at Lv.10)"
            return (f"🦸 Lands of Jail — Generation {g} Heroes", GENERATION_HEROES[g] + extra)

    # 8. Shield / Anti-Scout / Buff Diamond Prices
    if any(w in q_low for w in ("shield cost", "shield price", "anti scout", "anti-scout", "buff cost", "buff price", "training capacity buff", "gathering speed buff")) or (("shield" in tokens or "shields" in tokens) and any(w in q_low for w in ("2h", "8h", "24h", "72h", "how much", "cost", "price", "diamond"))):
        return (
            "🛡️ Shields & Combat Buff Diamond Prices",
            "• **Peace Shields:** 2h `800` 💎 | 8h `2,400` 💎 | 24h `9,600` 💎 | 72h `40,000` 💎 *(plus 5 free 8h shields recharging 1/24h)*\n"
            "• **Anti-Scout:** 2h `800` 💎 | 8h `2,400` 💎 | 24h `9,600` 💎\n"
            "• **Troop ATK / DEF / HP / Lethality (or Enemy Debuff):** +11% (2h) `4,000` 💎 | +22% (12h) `40,000` 💎\n"
            "• **Expedition Capacity:** +11% (2h) `4,000` 💎 | +22% (12h) `40,000` 💎\n"
            "• **Training Capacity (+210% for 2h):** `6,000` 💎 *(also adds +210% training time)*\n"
            "• **Gathering Speed (+110%):** 8h `300` 💎 | 24h `1,200` 💎",
        )

    # 9. Specific Upgrade Material lookup (Bolts, Magnets, Potential Coils, Precision Gear, Orbit/Cosmic Cores)
    if any(w in q_low for w in ("potential coil", "potential coils", "bolts", "where to get magnets", "where to get precision", "orbit core", "cosmic core", "skill book", "arrest guide", "war skill book")):
        return (
            "🔩 Lands of Jail — Upgrade Materials & Where to Get Them",
            "• **Bolts:** Hero equipment levels (up to Lv.200) → *Arrest Operation, Intelligence Tasks, Ultimate Trial, VIP Shop*\n"
            "• **Magnets:** Hero equipment promotions (Lv.100+) & Reformation (Lv.10+) → *Arena Shop, SvS ranking rewards, Equipment Packs*\n"
            "• **Potential Coils:** Hero equipment promotions to Legendary T2+ → *Arena Shop, Potential Packs*\n"
            "• **Precision Gear:** Equipment Reformation (Lv.1–20) → *Ultimate Trial, Black Market Merchant, Reformation Packs*\n"
            "• **Exclusive Equipment Parts:** Hero Exclusive Equipment (550 to Lv.10) → *Parts Choice Chests, events, Flea Market (Gen 1)*\n"
            "• **Orbit / Cosmic Cores:** Cosmos Hub Satellite Overclock (Lv.20+) → *Cosmos Hub & Laser Gathering Chests*\n"
            "• **Skill Books:** Arrest Guides & War Skill Books must match hero rarity (Blue=Rare, Pink=Epic, Yellow=Legendary).",
        )

    # 10. Individual Hero Lookup (if user specifically asks about 1 hero by name)
    if not any(w in tokens for w in ("lineup", "lineups", "tier", "leaders", "joiners", "all", "season")):
        matched_heroes = []
        for h_key, h_info in HERO_DIRECTORY.items():
            if h_key in tokens:
                if h_info[0] not in [m[0] for m in matched_heroes]:
                    matched_heroes.append(h_info)
        if len(matched_heroes) == 1:
            name, cls, gen, summary = matched_heroes[0]
            return (
                f"🦸 Hero Guide — {name} ({cls} • {gen})",
                summary,
            )

    return None
