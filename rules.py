import json

from config import GRADE_SCALE, PASS_MARK
from database import get_grade_rule_rows


def default_rules():
    return {"pass_mark": PASS_MARK, "grade_scale": GRADE_SCALE}


def load_rules():
    rules = {}
    for student_class, pass_mark, grade_scale_json in get_grade_rule_rows():
        try:
            scale = [(int(entry[0]), str(entry[1])) for entry in json.loads(grade_scale_json)]
        except (ValueError, TypeError):
            scale = GRADE_SCALE
        rules[student_class] = {"pass_mark": pass_mark, "grade_scale": scale}
    return rules


def for_class(student_class, rules):
    if rules and student_class in rules:
        return rules[student_class]
    return default_rules()


def dump_scale(scale):
    return json.dumps([[minimum, grade] for minimum, grade in scale])


def parse_scale(text):
    scale = []
    for line in text.splitlines():
        line = line.strip()
        if line == "":
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            continue
        try:
            minimum = int(float(parts[0]))
        except ValueError:
            continue
        scale.append((minimum, " ".join(parts[1:])))
    return sorted(scale, key=lambda entry: entry[0], reverse=True)
