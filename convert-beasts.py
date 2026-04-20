import argparse
import json
import math
import re

import pandas as pd

SIZE_INCREASE = {
    "T": "S",
    "S": "M",
    "M": "L",
    "L": "H",
    "H": "G",
    "G": "G",
}

SKILL_TO_ATTRIBUTE = {
    "athletics": "str",
    "acrobatics": "dex",
    "sleight of hand": "dex",
    "stealth": "dex",
    "arcana": "int",
    "history": "int",
    "investigation": "int",
    "nature": "int",
    "religion": "int",
    "animal handling": "wis",
    "insight": "wis",
    "medicine": "wis",
    "perception": "wis",
    "survival": "wis",
    "deception": "cha",
    "intimidation": "cha",
    "performance": "cha",
    "persuasion": "cha",
}

DROP_COLUMNS = ["page", "srd52", "basicRules2024", "referenceSources"]


def proficiency_bonus(level: float) -> int:
    return max(math.ceil(level / 4) + 1, 2)


def cr_to_float(cr: str | dict) -> float:
    if isinstance(cr, dict):
        cr = cr["cr"]
    if "/" in cr:
        numerator, denominator = cr.split("/")
        return float(numerator) / float(denominator)
    return float(cr)


def map_size(sizes: list[str]) -> list[str]:
    return [SIZE_INCREASE[size] for size in sizes]


def get_modifier(score: int) -> int:
    return (score - 10) // 2


def update_hp(row: pd.Series, level: int) -> dict:
    hit_dice = int(row["hp"]["formula"].split("d")[1].split(" ")[0])
    modifier = get_modifier(row["con"])
    cr = cr_to_float(row["cr"])
    flying = "fly" in row["speed"]
    multiplier = 0.5 if flying else 1
    total = math.floor(
        ((hit_dice + modifier) * level + math.floor(5 * cr)) * multiplier
    )
    formula = f"{level}d{hit_dice} {'+' if modifier > 0 else '-'} {abs(modifier * level)} + {math.floor(5 * cr)}"
    if flying:
        formula = f"({formula}) / 2"
    return {"average": total, "formula": formula}


def update_skills(row: pd.Series, level: int) -> dict:
    skills = row["skill"]
    if not isinstance(skills, dict):
        return skills

    og_prof = proficiency_bonus(cr_to_float(row["cr"]))
    for skill, mod in skills.items():
        attribute = SKILL_TO_ATTRIBUTE[skill]
        attribute_mod = get_modifier(row[attribute])
        og_attribute_mod = attribute_mod
        if attribute == "str" or attribute == "con":
            og_attribute_mod -= 1
        elif attribute == "dex":
            og_attribute_mod += 1

        factor = (int(mod) - og_attribute_mod) / og_prof
        skills[skill] = f"{proficiency_bonus(level) * factor + attribute_mod:+}"

    return skills


def update_saves(row: pd.Series, level: int) -> dict:
    saves = row["save"]
    if not isinstance(saves, dict):
        return saves

    og_prof = proficiency_bonus(cr_to_float(row["cr"]))
    for save, mod in saves.items():
        attribute_mod = get_modifier(row[save])
        og_attribute_mod = attribute_mod
        if save == "str" or save == "con":
            og_attribute_mod -= 1
        elif save == "dex":
            og_attribute_mod += 1

        factor = (int(mod) - og_attribute_mod) / og_prof
        saves[save] = f"{proficiency_bonus(level) * factor + attribute_mod:+}"

    return saves


def update_actions(row: pd.Series, level: int) -> list[dict]:
    actions = row["action"]
    if not isinstance(actions, list):
        return actions

    for i in range(len(actions)):
        for j in range(len(actions[i]["entries"])):
            s = actions[i]["entries"][j]
            matches = re.findall(r"{@hit (.+?)}", s)
            if matches:
                modifier = int(matches[0]) - proficiency_bonus(cr_to_float(row["cr"]))
                adjustment = -1
                if modifier == get_modifier(row["str"]) - 1:
                    adjustment = 1
            else:
                break

            s = re.sub(
                r"{@hit (.+?)}",
                f"{{@hit {modifier + adjustment + proficiency_bonus(level)}}}",
                s,
            )
            s = re.sub(
                r"{@damage (\d+d\d+)(.*?)}",
                lambda m: (
                    f"{{@damage {m.group(1)} {'+' if int(m.group(2).replace(' ', '') or 0) + adjustment > 0 else '-'} {int(m.group(2).replace(' ', '') or 0) + adjustment}}}"
                ),
                s,
            )
            s = re.sub(
                r"{@h}(\d+)", lambda m: f"{{@h {int(m.group(1)) + adjustment}}}", s
            )
            actions[i]["entries"][j] = s

    return actions


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Monster Manual beasts to 5 Banners Burning stat blocks."
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Path to the source monster JSON file (default: ./mm.json)",
        required=True,
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to write the output JSON file (default: ./5bb-beasts.json)",
        required=True,
    )
    parser.add_argument(
        "--level",
        type=int,
        help="Character level used for HP and proficiency scaling (default: 3)",
        required=True,
    )
    parser.add_argument(
        "--ac-mod",
        type=int,
        help="Flat AC bonus applied to all beasts (default: 3)",
        required=True,
    )
    parser.add_argument(
        "--only-beasts",
        type=bool,
        help="Whether to only include beasts in the output (default: True)",
    )

    args = parser.parse_args()

    print(f"Reading monsters from {args.input} ...")
    with open(args.input, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["monster"])
    if args.only_beasts:
        df = df[
            (df["type"] == "beast")
            | (
                df["type"].apply(
                    lambda x: isinstance(x, dict) and x.get("type") == "beast"
                )
            )
        ]

    print(f"Found {len(df)} monsters.")

    df["name"] = df["name"] + " (5BB)"
    df["source"] = "5BB"
    existing_drop = [c for c in DROP_COLUMNS if c in df.columns]
    df = df.drop(columns=existing_drop)
    df["size"] = df["size"].apply(map_size)
    df["str"] += 2
    df["dex"] -= 2
    df["con"] += 2

    ac_is_int = df["ac"].apply(lambda x: isinstance(x[0], int))
    df.loc[ac_is_int, "ac"] = df[ac_is_int]["ac"].apply(lambda x: [x[0] + args.ac_mod])
    df.loc[~ac_is_int, "ac"] = df[~ac_is_int]["ac"].apply(
        lambda x: [x[0] | {"ac": x[0]["ac"] + args.ac_mod}]
    )

    df["hp"] = df.apply(update_hp, axis=1, level=args.level)
    df["skill"] = df.apply(update_skills, axis=1, level=args.level)
    df["save"] = df.apply(update_saves, axis=1, level=args.level)
    df["action"] = df.apply(update_actions, axis=1, level=args.level)

    output = {
        "monster": [row.dropna().to_dict() for _, row in df.iterrows()],
        "_meta": {
            "sources": [
                {
                    "json": "5BB",
                    "abbreviation": "5BBTmp",
                    "full": "5 Banners Burning (Tmp)",
                    "version": "0.1.0",
                    "authors": ["Josias Brenner"],
                    "convertedBy": ["Josias Brenner"],
                    "color": "b8411a",
                }
            ],
            "dateAdded": 1776156420,
            "dateLastModified": 1776625838,
            "edition": "one",
            "status": "wip",
        },
    }

    print(f"Writing output to {args.output} ...")
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2)
    print("Done.")


if __name__ == "__main__":
    main()
