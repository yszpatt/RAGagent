def should_no_answer(top_score: float, threshold: float = 0.3) -> bool:
    return top_score < threshold
