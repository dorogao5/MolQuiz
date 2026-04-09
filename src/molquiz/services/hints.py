from __future__ import annotations


def build_hints(descriptor_snapshot: dict, molecular_formula: str) -> list[str]:
    functional_groups = descriptor_snapshot.get("functional_groups") or []
    topic_tags = descriptor_snapshot.get("topic_tags") or []
    ring_count = descriptor_snapshot.get("ring_count", 0)
    longest_chain = descriptor_snapshot.get("longest_chain", 0)
    substituent_count = descriptor_snapshot.get("substituent_count", 0)

    class_hint_parts = []
    if "aromatic" in topic_tags:
        class_hint_parts.append("ароматическое")
    elif ring_count:
        class_hint_parts.append("циклическое")
    else:
        class_hint_parts.append("алифатическое")

    if functional_groups:
        class_hint_parts.append(f"с группами: {', '.join(functional_groups)}")
    else:
        class_hint_parts.append("без выраженных функциональных групп")

    return [
        f"Класс: {' '.join(class_hint_parts)}.",
        f"Молекулярная формула: {molecular_formula}.",
        f"Подсказка: главная цепь около {longest_chain} атомов, заместителей около {substituent_count}.",
    ]
