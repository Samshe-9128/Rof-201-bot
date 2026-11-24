# core/knowledge_defaults.py
"""Shared default Knowledge Base entries for Haven (HAV) — Server 201 & Lands of Jail Wiki."""

DEFAULT_KNOWLEDGE_ENTRIES = [
    # --- Bot Identity & Haven Alliance ---
    {
        "key": "bot_about",
        "title": "About HAV Bot & Creator (Sam — Server 201)",
        "category": "About",
        "content": (
            "I'm the **HAV Bot**, the official alliance assistant and gaming bot for **Haven (`HAV`)** on **Server 201** in **Lands of Jail**!\n\n"
            "• **Built by:** **Sam** (Server 201)\n"
            "• **What I do:** Track alliance events in Game Time & India Time (`/events`), share alliance rules (`/rules view`), "
            "answer **Lands of Jail** strategy questions (heroes, Trial Cage, SvS, Crystal Clash, buildings, Cosmos Hub), and host 22 single-player & multiplayer Discord games (`/games`)."
        ),
        "keywords": "who are you who made you who built you who created you about yourself bot owner developer sam server 201 haven hav",
    },
    {
        "key": "surge_guide",
        "title": "Turmoil Surge Event Guide",
        "category": "Events",
        "content": (
            "During **Turmoil Surge**, rally and reinforce online alliance members at the scheduled Game Time. "
            "Upgrade your **Communication Centre** to hold more ally reinforcements, check `/events` for exact Game Time & IST schedules, and be ready 10 minutes before launch."
        ),
        "keywords": "surge turmoil surge event guide schedule rally reinforce communication centre",
    },
    {
        "key": "codebreaker_help",
        "title": "How to Play Four-Digit Codebreaker",
        "category": "Games",
        "content": (
            "Create or join a Codebreaker room via `/games` or `/codebreaker`. The bot generates a 4-digit secret code with unique digits (no leading zero). "
            "Submit 4-digit guesses; 🟢 shows digits in the exact position and 🟡 shows correct digits in the wrong position."
        ),
        "keywords": "codebreaker how to play 4 digit secret code clues mastermind",
    },
    {
        "key": "event_permissions",
        "title": "Who Can Schedule Alliance Events",
        "category": "FAQ",
        "content": (
            "Only authorized administrators and the bot owner (**Sam**) can create, edit, or delete alliance events. "
            "All Haven members can view upcoming events anytime using `/events`."
        ),
        "keywords": "schedule create add modify cancel event permission admin who can",
    },
    {
        "key": "member_responsibilities",
        "title": "HAV Member Responsibilities",
        "category": "Guides",
        "content": (
            "Stay active on **Server 201**, contribute to alliance tech donations daily, tap **Alliance Help** consistently, check `/events` for upcoming battles, "
            "and treat fellow **Haven (HAV)** members with respect."
        ),
        "keywords": "member responsibilities duties donations active rules guide haven hav server 201",
    },

    # --- Lands of Jail Wiki Knowledge Base (landsofjail.miraheze.org) ---
    {
        "key": "loj_hero_leaders",
        "title": "Lands of Jail — Best Rally Leaders (Seasons 1–7)",
        "category": "Heroes",
        "content": (
            "For leading rallies (especially Trial Cage), a leader's **full kit** counts (all 3 heroes and all war skills):\n\n"
            "• **S-Tier Leaders:** **Tyronn** *(Shieldbearer — #1 once exclusive gear is built; otherwise Phoenix)*, **Wukong** *(Bomber)*, **Ada** *(Shooter)*.\n"
            "• **A-Tier Leaders:** **Phoenix**, **Ryuichi Ito** *(beats Koschevoi near max exclusive gear)*, **Rin**, **Sawyer** *(scales the full rally)*.\n"
            "• **B-Tier Leaders:** **Otto**, **Koschevoi**, **Boogie**, **Whisper**, **Kate**, **Mireya**, **Edwin**.\n"
            "• **Avoid as Leaders (D-Tier):** Mia, Tormund, Inata, Gerd, Gimes, Platos, Vesaryon, Caesar.\n"
            "• **Trial Cage Leader Troops:** ~`0% Shieldbearers / 10% Bombers / 90% Shooters` (`1% / 9% / 90%` with Ada leading)."
        ),
        "keywords": "lands of jail loj hero heroes tier list rally leader leaders best tyronn wukong ada phoenix sawyer ryuichi ito rin",
    },
    {
        "key": "loj_hero_joiners",
        "title": "Lands of Jail — Best Rally Joiners & Joiner Rules",
        "category": "Heroes",
        "content": (
            "When you **join** a rally, **only the 1st war skill of your 1st hero** counts, and only the **top 4 joiner skills** in the rally apply:\n\n"
            "• **S-Tier Joiners:** **Tyronn**, **Phoenix**, **Lunarl** *(SR)*, **Minyeon & Taehun** *(SR)*, **Veronica**, **Koschevoi**, **Whisper** *(−20% enemy DEF guaranteed)*.\n"
            "• **A-Tier Joiners:** **Lofili**, **Vivian**, **Samir**, **Kate**, **Ryuichi Ito**.\n"
            "• **Avoid as Joiners (D-Tier):** Mia, Inata, Platos, Aiksen, Durga, Gerd, Tormund, Harton, Vesaryon, Flora, Iwado, Gimes, Pasino.\n"
            "• **Important Rules:** Don't double up the same buff in one rally—coordinate in chat! In **Trial Cage**, Lethality/DEF/HP skills don't count toward score, but they **do** matter in **SvS / Supreme Prison** (where Alph, Ekko, Mireya shine)."
        ),
        "keywords": "lands of jail loj rally joiner joiners first skill whisper lunarl minyeon taehun veronica koschevoi phoenix tyronn lofili",
    },
    {
        "key": "loj_season_lineups",
        "title": "Lands of Jail — Best Hero Lineups by Season",
        "category": "Heroes",
        "content": (
            "Community reference squads (**Shieldbearer / Bomber / Shooter**) by server season:\n\n"
            "**Rally Lineups:**\n"
            "• **S1:** Tyronn / Vivian / Devilian • **S2:** Tyronn / Vivian / Mireya\n"
            "• **S3:** Tyronn / Whisper / Sawyer • **S4:** Tyronn / Ryuichi Ito / Sawyer\n"
            "• **S5:** Tyronn / Ryuichi Ito / Ada *(or Tyronn / Whisper / Ada)* • **S6–7 add:** Wukong, Rin\n\n"
            "**Garrison / Defense:**\n"
            "• **S2:** Caesar / Lanchester / Inata • **S3:** Xuanming / Lanchester / Inata\n"
            "• **S4:** Zoltan / Lanchester / Drake • **S5:** Marcus / Lee / Drake • **S6–7 add:** Otto, Kate, Fran & Pike, Boogie\n\n"
            "**Solo Attack:**\n"
            "• **S3:** Phoenix / Alph / Veronica • **S4:** Phoenix / Koschevoi / Veronica • **S5:** Phoenix / Koschevoi / Edwin • **S6–7 add:** Worrell, Rex"
        ),
        "keywords": "lands of jail loj lineup lineups team composition squad season s1 s2 s3 s4 s5 s6 s7 garrison defense solo rally marcus zoltan xuanming",
    },
    {
        "key": "loj_utility_heroes",
        "title": "Lands of Jail — Utility, Speed & Gathering Heroes",
        "category": "Heroes",
        "content": (
            "Keep these heroes for their **non-combat utility bonuses** (don't send gathering R heroes into war rallies):\n\n"
            "• **Mia (S):** −20% stamina cost & +100% march speed against field enemies.\n"
            "• **Vivian (S):** +15% building speed & −15% building cost.\n"
            "• **Inata (S):** +15% research speed.\n"
            "• **Devilian (S):** +30% troop training speed.\n"
            "• **Minyeon & Taehun / Rex (A):** Extra damage against monsters.\n"
            "• **Durga, Harton, Pasino, Aiksen (A):** Factory profit & resource gathering bonuses."
        ),
        "keywords": "lands of jail loj utility economy gathering speed mia vivian inata devilian durga harton pasino aiksen stamina research building training",
    },
    {
        "key": "loj_buildings_exterior",
        "title": "Lands of Jail — Exterior Building Upgrade Order",
        "category": "Buildings",
        "content": (
            "Recommended exterior upgrade order from the Lands of Jail Wiki:\n\n"
            "1. **Warden's Office:** Anchor for every other building level (Haven Island opens at **Office Lv.19**; Forticlad goes up to **Lv.10**).\n"
            "2. **Communication Centre:** Needed every tier—boosts ally reinforcement capacity (critical for Turmoil Surge & defense) and Alliance Help time reduction.\n"
            "3. **Barracks (`Shooters > Shieldbearers > Bombers`):** Always **promote** lower-tier troops whenever you unlock a new soldier tier!\n"
            "4. **Medical Station:** Upgrade right after Barracks so wounded troops heal instead of dying/waiting in Recruitment Hall during SvS & KE.\n"
            "5. **Research Lab & Forticlad Lab:** Logistics, Economy, Military (Forticlad Lab uses **Hyperalloy**, opens around server Day 230).\n"
            "6. **Inventory & Gate:** Inventory protects Food/Wood/Steel/Gasoline; upgrade Gate to Lv.10 and always put out fires."
        ),
        "keywords": "lands of jail loj building buildings upgrade order warden office communication centre barracks medical station lab forticlad hyperalloy inventory gate haven island",
    },
    {
        "key": "loj_buildings_interior",
        "title": "Lands of Jail — Interior Prison Rooms & Riot Prevention",
        "category": "Buildings",
        "content": (
            "Keep inmates working in the Factory without rioting by upgrading interior rooms in this order:\n\n"
            "1. **Guard Room:** Keeps guards strong enough to stop high-danger prisoner riots.\n"
            "2. **Factory:** Main Cash source; unlocks higher-value products and Fortune Arcade chips.\n"
            "3. **Kitchen + Cafeteria:** Upgrade together so all inmates are fed during both daily meal slots (hunger triggers riots).\n"
            "4. **Shower Rooms + Laundry:** Maintains Hygiene so low cleanliness doesn't spark riots.\n"
            "5. **Cells:** Bed/Lamp/Fan boost **Comfort**; Security Camera boosts **Obedience**; TV/Radio/Punching Bag/Bookshelf boost **Fun**.\n"
            "6. **Utility Room & Playground:** Janitors maintain Cleaning/Health/Laundry; Playground boosts Health & Fun."
        ),
        "keywords": "lands of jail loj interior prison rooms guard room factory kitchen cafeteria shower laundry cells utility playground riot cash hygiene",
    },
    {
        "key": "loj_cosmos_hub",
        "title": "Lands of Jail — Cosmos Hub, Satellites & Overclock",
        "category": "Systems",
        "content": (
            "**Cosmos Hub** satellites provide major passive and Arrest/Gorilla bonuses:\n\n"
            "• **Core Satellites:** **Watcher** *(once maxed: daily 5-hour instant Arrest reward)*, **Laser** *(up to 5 Gathering Chests/day: Planet Coins, Data Disks, Orbit/Cosmic Cores)*, **Radiance** *(+5% DMG / −5% DMG taken in Arrests)*.\n"
            "• **SR / SSR Satellites:** Sentinel, Arbitrator (SR); Argus, Polaris, Omniscient Domain, Sky Nexus, Crystal Matrix, Territory Sentinel (SSR). Satellite bonuses are boosted **×1000%** vs the Monday **Space Gorilla**!\n"
            "• **Overclock:** Unlocks at Satellite **Lv.20** (Rare Lv.20, Epic Lv.30, Exotic Lv.40) using Orbit/Cosmic Cores to boost Bomber & Shieldbearer Lethality/HP.\n"
            "• **Cosmic Exploration:** Send your vessel on 23-hour missions daily (extra vessels can be rented for 7 days with Diamonds)."
        ),
        "keywords": "lands of jail loj cosmos cosmic hub satellite satellites watcher laser radiance overclock orbit core space gorilla exploration",
    },
    {
        "key": "loj_ultimate_trial",
        "title": "Lands of Jail — Ultimate Trial (Trial Cage / Scarlet Butcher)",
        "category": "Events",
        "content": (
            "• **Duration & Cooldown:** Lasts **30 minutes** against the **Imprisoned Scarlet Butcher**, followed by a **47-hour cooldown**.\n"
            "• **Core Strategy:** Launch **as many rallies as possible** in 30 minutes (each Warden launches 1 rally at a time while joining others' marches).\n"
            "• **Pre-Trial Buff:** Donate **Enhanced Chains** (from Intelligence Tasks) before start to boost alliance-wide damage.\n"
            "• **Best Felons:** **Scorpion** and **Cobra**.\n"
            "• **Best Troops & Joiners:** Leader ratio `0/10/90` (`1/9/90` with Ada); join with **Tyronn, Phoenix, Lunarl, Whisper, Veronica, Koschevoi** (Lethality/DEF/HP joiner skills do not add Trial Cage score)."
        ),
        "keywords": "lands of jail loj ultimate trial cage scarlet butcher boss enhanced chains scorpion cobra felon felons dmg",
    },
    {
        "key": "loj_svs",
        "title": "Lands of Jail — Supreme Honor (SvS) Complete Guide",
        "category": "Events",
        "content": (
            "**Supreme Honor (SvS)** pits two servers across 4 phases (Matching → 5-Day Prep → War → Recovery):\n\n"
            "**Preparation Phase (Save for matching days!):**\n"
            "• **Day 1:** Forticlad Cores (3k), Speedups (90/min), Tome Rating (210)\n"
            "• **Day 2:** Forticlad Cores, Speedups, Reinforcement Spin (24k), Hero Shards (Rare 1,050 / Epic 3,660 / Leg 9,120), Gathering\n"
            "• **Day 3:** Power Modules (1.3k / Adv 6.5k), Module Chests, Tome, Spin, Hero Shards, Beast Rallies (90k), Fugitives\n"
            "• **Day 4:** Tome, Precision Gear (6k), Hero Exclusive Equip Parts (12k), Soldier Training (Lv.10 = 180 pts)\n"
            "• **Day 5:** Power Modules, Module Chests, Tome, Precision Gear, Exclusive Equip, Forticlad Cores, Speedups\n\n"
            "**War & Recovery:** Winner of Prep invades the losing server's **Supreme Prison** (hold 2 consecutive hours or longest total to win). "
            "Recovery revives **35% base up to 95% max** via **Gene Capsules** (+1% up to 10%) and ally **Rescue Capsules** (receive up to 50 rescues). *Never leave the alliance before settlement or you forfeit rewards!*"
        ),
        "keywords": "lands of jail loj svs supreme honor prep preparation day 1 day 2 day 3 day 4 day 5 war recovery revival gene rescue capsules supreme prison",
    },
    {
        "key": "loj_crystal_clash",
        "title": "Lands of Jail — Crystal Clash Rules & Buildings",
        "category": "Events",
        "content": (
            "**Crystal Clash** is a 1-hour alliance vs alliance battlefield (Top 20 alliances; **Warden's Office Lv.16+**; max 30 Starters + 10 Reserves per Legion):\n\n"
            "• **Before Entering:** No marching/scouting troops, **0 wounded** in Medical Station, Gate not burning, no reinforcements in Comms Center.\n"
            "• **Zero Permanent Deaths:** All wounded go to an unlimited free Infirmary and auto-heal when the battle ends! (10-min cooldown if you leave midway.)\n"
            "• **Key Buildings:** **Crystal Ironprison & Ironhold** (+12k first / +2,400/min), **Crystal Prison** (+4k / +800/min), **Pillbox** (+15% Troop Lethality & +15% HP), **Energy Hub** (−50% Fixed Teleport cooldown), **Refinement Center** (−50% control time), **Bomber Command Center** (airstrikes reducing enemy ATK/DEF)."
        ),
        "keywords": "lands of jail loj crystal clash arena legion stronghold ironprison ironhold pillbox energy hub refinement center bomber command",
    },
    {
        "key": "loj_other_events",
        "title": "Lands of Jail — Brawl, Sandsea Conquest, Dreadwaker & Treasure Barrage",
        "category": "Events",
        "content": (
            "• **Alliance Brawl:** Runs on a 4-week cycle—save speedups, troop training, and upgrades for matching scoring days.\n"
            "• **Sandsea Conquest:** Cross-alliance desert battlefield where **Fuel** is used for fast movement.\n"
            "• **Dreadwaker Overlord:** Server-vs-server battle for the **Overlord Nexus** featuring Defense Erosion against Nexus defenders and Colossus buffs.\n"
            "• **Treasure Barrage & Riot Runway:** Seasonal reward events (Treasure Barrage replaced Project Chamber; Riot Runway features card races)."
        ),
        "keywords": "lands of jail loj alliance brawl sandsea conquest fuel dreadwaker overlord nexus colossus treasure barrage riot runway",
    },
    {
        "key": "loj_troops",
        "title": "Lands of Jail — Troop Types & Formation Ratios",
        "category": "Strategy",
        "content": (
            "Three troop classes: **Shieldbearers** (frontline tank), **Bombers** (secondary offense), and **Shooters** (primary DPS):\n\n"
            "• **Trial Cage Rallies:** `0% Shieldbearers / 10% Bombers / 90% Shooters` (`1% / 9% / 90%` with Ada leading).\n"
            "• **Alliance War Rallies (Balanced):** `20% Shieldbearers / 30% Bombers / 50% Shooters`.\n"
            "• **Fast Offense / Plunder:** `10% Shieldbearers / 20% Bombers / 70% Shooters`.\n"
            "• **Garrison Defense:** `40% Shieldbearers / 30% Bombers / 30% Shooters`."
        ),
        "keywords": "lands of jail loj troop troops ratio ratios formation shieldbearers bombers bombardiers shooters rally garrison plunder",
    },
    {
        "key": "loj_equipment",
        "title": "Lands of Jail — Hero Equipment Upgrade Priority",
        "category": "Strategy",
        "content": (
            "Upgrade hero equipment in order of combat impact:\n\n"
            "1. **Firearms (Shooters):** #1 overall priority for rally offense, Trial Cage, and Gorilla bosses.\n"
            "2. **Bulletproof Vests (Shieldbearers):** #1 priority for dedicated garrison defenders, #2 overall.\n"
            "3. **Tactical Weapons (Bombers):** Secondary offensive priority for mixed war formations.\n"
            "4. **Masks (All Types):** Upgrade last after primary troop gear."
        ),
        "keywords": "lands of jail loj equipment gear firearms bulletproof vest vests tactical weapons masks upgrade priority",
    },
    {
        "key": "loj_currency",
        "title": "Lands of Jail — Diamonds & Gold Cuffs Spending Guide",
        "category": "Strategy",
        "content": (
            "• **Diamonds:** Prioritize Universal Speed-Ups during SvS/Brawl scoring windows, Supply Cards for top rally leaders (**Tyronn / Wukong / Ada**), and Cosmos Hub / event milestones.\n"
            "• **Gold Cuffs:** Earned from top-up bonuses and **Treasure Dice** milestones—spend on Training Camp & Hero Equipment bundles first rather than plain resource packs."
        ),
        "keywords": "lands of jail loj diamonds gold cuffs currency spend spending supply cards treasure dice packs",
    },
    {
        "key": "loj_codes",
        "title": "Lands of Jail — How to Redeem Gift Codes",
        "category": "FAQ",
        "content": (
            "To claim free Diamonds, Legendary Hero Shards, and Speed-Ups from **Lands of Jail** gift codes:\n"
            "1. Open **Lands of Jail** (mobile or official PC version).\n"
            "2. Tap your **Profile** avatar in the top-left corner.\n"
            "3. Open **Settings** → tap **REDEEM**.\n"
            "4. Enter the gift code *(case-sensitive)* and tap **Redeem**."
        ),
        "keywords": "lands of jail loj gift code codes redeem promo free diamonds shards rewards pc version",
    },
    {
        "key": "loj_exclusive_weapons",
        "title": "Lands of Jail — Exclusive Equipment Upgrade Costs (Lv.0–10)",
        "category": "Equipment",
        "content": (
            "Maxing one hero's **Exclusive Equipment** from **Lv.0 → Lv.10** costs **550 Parts** total (steps climb in pairs):\n"
            "`0→1: 10` | `1→2: 25` | `2→3: 25` | `3→4: 45` | `4→5: 45` | `5→6: 65` | `6→7: 65` | `7→8: 85` | `8→9: 85` | `9→10: 100`\n\n"
            "• **Skill Rhythm:** Odd levels upgrade **Arrest** skill; Even levels upgrade **War** skill.\n"
            "• **Season Troop Bonus/Lvl:** S1 `+5.25%` | S2 `+6.3%` | S3 `+7.35%` | S4 `+9.7%` | S5 `+11.7%` | S6 `+14%` *(Exceptions: Tyronn +73.5%, Phoenix +65.63%; Mia has none)*.\n"
            "• **Ask any range:** Type e.g. *'exclusive equipment lvl 5 to lvl 6'* for instant parts & SvS Day 4/5 points!"
        ),
        "keywords": "lands of jail loj exclusive equipment weapon weapons parts upgrade cost level 0 10 pairs brutal gauntlets colossus hammer divine power",
    },
    {
        "key": "loj_reformation",
        "title": "Lands of Jail — Equipment Reformation Costs (Lv.1–20)",
        "category": "Equipment",
        "content": (
            "**Mastery Reformation** uses **Precision Gear** every level (`4,260` total for Lv.1–20) and adds **Magnets** starting at **Lv.10** (`11,220` total for Lv.10–20):\n"
            "• **Lv.1–9 (900 Gears total):** `20, 40, 60, 80, 100, 120, 140, 160, 180` Precision Gears (0 Magnets).\n"
            "• **Lv.10 Wall:** Lv.10 takes `200G + 220M`, Lv.15 takes `300G + 1,000M`, Lv.20 takes `400G + 2,000M`.\n"
            "• **Ask any range:** Type e.g. *'reformation lvl 5 to lvl 10'* for exact Gears, Magnets & SvS points!"
        ),
        "keywords": "lands of jail loj equipment reformation mastery reform precision gear magnets level 1 20 cost",
    },
    {
        "key": "loj_tomes",
        "title": "Lands of Jail — Tome Upgrade Costs (Lv.0–18)",
        "category": "Systems",
        "content": (
            "Each troop type (Shield, Bomber, Shooter) has **6 Tomes** (Lv.0 → Lv.18, up to **250%** bonus):\n"
            "• **Lv.0 → 12 (Halfway, 126% bonus):** `5,320` Wisdom + `6,410` Knowledge per tome (`0` Mystery Tome).\n"
            "• **Lv.12 → 18 (250% max):** Adds **Seal of Mystery Tome** (`8, 15, 22, 35, 50, 66` = `196` per tome).\n"
            "• **Full 1 Tome (0 → 18):** `11,940` Wisdom + `14,590` Knowledge + `196` Mystery Tome.\n"
            "• **Ask any range:** Type e.g. *'tome lvl 5 to lvl 12'* for exact seal totals!"
        ),
        "keywords": "lands of jail loj tome tomes seal wisdom knowledge mystery tome upgrade cost level 0 18",
    },
    {
        "key": "loj_items_buffs",
        "title": "Lands of Jail — Shields, Combat Buffs & Upgrade Materials",
        "category": "FAQ",
        "content": (
            "• **Shields (💎):** 2h `800` | 8h `2,400` | 24h `9,600` | 72h `40,000` *(+5 free 8h shields recharging 1/24h)*\n"
            "• **Combat Buffs (💎):** +11% ATK/DEF/HP/Lethality (2h) `4,000` | +22% (12h) `40,000` | Gathering +110% (8h `300`, 24h `1,200`) | Training +210% (2h `6,000`)\n"
            "• **Materials:** **Bolts** (Gear Lv.1–200), **Magnets** (Promotions Lv.100+ & Reformation Lv.10+), **Potential Coils** (Legendary T2+), **Precision Gear** (Reformation), **Parts Choice Chests** (Exclusive Equipment), **Orbit/Cosmic Cores** (Satellite Overclock)."
        ),
        "keywords": "lands of jail loj items buffs shields anti scout diamond price bolts magnets potential coils precision gear skill books",
    },
]
