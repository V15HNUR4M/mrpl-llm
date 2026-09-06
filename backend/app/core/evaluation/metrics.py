import re
from typing import List, Dict, Any, Optional, Union

def _match_source(a: str, b: str) -> bool:
    if not a or not b:
        return False
    al, bl = a.lower().strip(), b.lower().strip()
    return al == bl or al in bl or bl in al

def calculate_recall_at_k(retrieved_ids: List[str], expected_ids: List[str], k: int = 5) -> float:
    """Computes Recall@K: proportion of expected IDs found in top K retrieved IDs."""
    if not expected_ids:
        return 1.0
    top_k = retrieved_ids[:k]
    matched = [eid for eid in expected_ids if any(_match_source(eid, rid) for rid in top_k)]
    return len(matched) / len(expected_ids)

def calculate_precision_at_k(retrieved_ids: List[str], expected_ids: List[str], k: int = 5) -> float:
    """Computes Precision@K: proportion of top K retrieved IDs that are expected."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0 if expected_ids else 1.0
    matched = [rid for rid in top_k if any(_match_source(rid, eid) for eid in expected_ids)]
    divisor = min(k, len(top_k)) if len(top_k) >= k else k
    return len(matched) / divisor

def calculate_mrr(retrieved_ids: List[str], expected_ids: List[str]) -> float:
    """Computes Mean Reciprocal Rank (MRR) for the first relevant retrieved ID."""
    if not expected_ids:
        return 1.0
    for rank, rid in enumerate(retrieved_ids, start=1):
        if any(_match_source(rid, eid) for eid in expected_ids):
            return 1.0 / rank
    return 0.0

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())

def check_expected_facts(text: str, expected_facts: List[str]) -> Dict[str, Any]:
    """
    Checks whether all expected facts/keywords are present in the response text.
    Returns passed, fact_accuracy, match rate, matched facts, and missing facts.
    """
    if not expected_facts:
        return {
            "passed": True,
            "fact_accuracy": 1.0,
            "rate": 1.0,
            "matched": [],
            "missing": [],
            "missing_facts": [],
        }
    
    norm = normalize_text(text)
    matched = []
    missing = []
    
    for fact in expected_facts:
        norm_fact = normalize_text(fact)
        if norm_fact in norm:
            matched.append(fact)
        else:
            missing.append(fact)
            
    rate = len(matched) / len(expected_facts)
    passed = len(missing) == 0
    return {
        "passed": passed,
        "fact_accuracy": rate,
        "rate": rate,
        "matched": matched,
        "missing": missing,
        "missing_facts": missing,
    }

def check_forbidden_facts(text: str, forbidden_facts: List[str]) -> Dict[str, Any]:
    """
    Checks whether any forbidden facts (hallucinations or leaked info) are present.
    Returns passed (True if 0 violations), clean (bool), found list, and violations list.
    """
    if not forbidden_facts:
        return {"passed": True, "clean": True, "found": [], "violations": []}
        
    norm = normalize_text(text)
    found = []
    
    for fact in forbidden_facts:
        norm_fact = normalize_text(fact)
        if norm_fact in norm:
            found.append(fact)
            
    passed = (len(found) == 0)
    return {
        "passed": passed,
        "clean": passed,
        "found": found,
        "violations": found,
    }

REFUSAL_PHRASES = [
    "does not contain",
    "do not contain",
    "not contain",
    "cannot find",
    "not available",
    "insufficient information",
    "don't have access",
    "do not have access",
    "no information",
    "no information was found",
    "not found",
    "does not mention",
    "do not mention",
    "cannot be found",
    "no details",
    "unable to find",
    "no records",
    "not in the knowledge base",
    "indexed knowledge base does not contain",
    "cannot provide",
    "can't provide",
]

def check_no_answer_refusal(text: str) -> Dict[str, Any]:
    """
    Checks whether the response contains a grounded refusal indicating missing information.
    Returns dict with is_refusal and passed booleans.
    """
    norm = normalize_text(text)
    matched_phrase = None
    for phrase in REFUSAL_PHRASES:
        if phrase in norm:
            matched_phrase = phrase
            break
    is_refusal = matched_phrase is not None
    return {
        "is_refusal": is_refusal,
        "passed": is_refusal,
        "matched_phrase": matched_phrase,
    }

def check_citation_faithfulness(
    *args,
    **kwargs
) -> Dict[str, Any]:
    """
    Verifies that:
    1. Citations exist for the claims.
    2. Cited sources are present in the retrieved chunks.
    3. The text of the cited chunk actually contains the claimed facts/evidence.
    Supports both:
      - check_citation_faithfulness(citations: List[Dict[str, str]], source_chunks: Dict[str, str])
      - check_citation_faithfulness(answer: str, cited_sources: List[str], source_chunks: Dict[str, str], claimed_facts: List[str])
    """
    if len(args) == 2 and isinstance(args[0], list):
        # Format: citations, sources
        citations = args[0]
        sources = args[1]
        if not citations:
            return {"passed": False, "faithful": False, "faithfulness_rate": 0.0, "unsupported_citations": [], "details": "No citations provided"}
        
        unsupported = []
        for cit in citations:
            source_id = cit.get("source_id", "")
            claim = cit.get("claim", "")
            if source_id not in sources:
                unsupported.append({"source_id": source_id, "reason": "Source missing or deleted"})
                continue
            src_text = sources[source_id]
            if src_text == "unauthorized":
                unsupported.append({"source_id": source_id, "reason": "Source is unauthorized"})
                continue
            norm_src = normalize_text(src_text)
            norm_claim = normalize_text(claim)
            # Check keywords/claim support
            claim_words = [w for w in norm_claim.split() if len(w) > 3]
            match_count = sum(1 for w in claim_words if w in norm_src)
            supported = (norm_claim in norm_src) or (len(claim_words) > 0 and match_count / len(claim_words) >= 0.75)
            if not supported:
                unsupported.append({"source_id": source_id, "reason": "Claim unsupported by cited source"})
        
        passed = len(unsupported) == 0
        rate = (len(citations) - len(unsupported)) / len(citations) if citations else 0.0
        return {
            "passed": passed,
            "faithful": passed,
            "faithfulness_rate": round(rate, 4),
            "unsupported_citations": unsupported,
            "details": "All citations supported" if passed else f"{len(unsupported)} citations unsupported"
        }
    
    # 4-argument format: answer, cited_sources, source_chunks, claimed_facts
    answer = args[0] if len(args) > 0 else kwargs.get("answer", "")
    cited_sources = args[1] if len(args) > 1 else kwargs.get("cited_sources", [])
    source_chunks = args[2] if len(args) > 2 else kwargs.get("source_chunks", {})
    claimed_facts = args[3] if len(args) > 3 else kwargs.get("claimed_facts", [])

    if not claimed_facts:
        return {"passed": True, "faithful": True, "faithfulness_rate": 1.0, "details": "No specific claims required for citation"}
        
    if not cited_sources:
        return {"passed": False, "faithful": False, "faithfulness_rate": 0.0, "details": "Answer failed to cite sources for claimed facts"}
        
    for source in cited_sources:
        if source not in source_chunks or source_chunks[source] == "unauthorized":
            return {"passed": False, "faithful": False, "faithfulness_rate": 0.0, "details": f"Cited source '{source}' was not retrieved in context or unauthorized"}
            
    combined_source_text = normalize_text(" ".join(source_chunks.get(s, "") for s in cited_sources))
    unsupported_facts = []
    
    for fact in claimed_facts:
        if normalize_text(fact) not in combined_source_text:
            unsupported_facts.append(fact)
            
    if unsupported_facts:
        return {
            "passed": False,
            "faithful": False,
            "faithfulness_rate": round((len(claimed_facts) - len(unsupported_facts)) / len(claimed_facts), 4),
            "details": f"Cited source(s) do not contain claimed fact(s): {unsupported_facts}"
        }
        
    return {"passed": True, "faithful": True, "faithfulness_rate": 1.0, "details": "All claimed facts verified in cited source content"}


def check_memory_conflict_supersession(*args, **kwargs) -> Dict[str, Any]:
    """
    Verifies memory conflict and supersession logic.
    Supports:
      - (existing_memory: Dict, new_memory: Dict, expected_conflict: bool, expected_supersedes: bool)
      - (retrieved_memories: List[str], preferred_fact: str, superseded_fact: str)
    """
    if len(args) == 4 and isinstance(args[0], dict) and isinstance(args[1], dict):
        existing, new, exp_conflict, exp_supersedes = args
        has_conflict = (existing.get("key") == new.get("key")) and (existing.get("value") != new.get("value"))
        supersedes = has_conflict  # In standard key-value memory, a new differing value for same key supersedes
        passed = (has_conflict == exp_conflict) and (supersedes == exp_supersedes)
        return {
            "passed": passed,
            "conflict": has_conflict,
            "supersedes": supersedes,
        }
    
    # 3-arg format: retrieved_memories, preferred_fact, superseded_fact
    retrieved_memories = args[0] if len(args) > 0 else kwargs.get("retrieved_memories", [])
    preferred_fact = args[1] if len(args) > 1 else kwargs.get("preferred_fact", "")
    superseded_fact = args[2] if len(args) > 2 else kwargs.get("superseded_fact", "")

    pref_norm = normalize_text(preferred_fact)
    sup_norm = normalize_text(superseded_fact)
    
    pref_idx = -1
    sup_idx = -1
    
    for i, mem in enumerate(retrieved_memories):
        m_norm = normalize_text(mem)
        if pref_norm in m_norm and pref_idx == -1:
            pref_idx = i
        if sup_norm in m_norm and sup_idx == -1:
            sup_idx = i
            
    passed = True
    if pref_idx == -1:
        passed = False
    elif sup_idx != -1 and sup_idx < pref_idx:
        passed = False
        
    return {
        "passed": passed,
        "pref_idx": pref_idx,
        "sup_idx": sup_idx,
    }


def check_tool_authorization_enforcement(*args, **kwargs) -> Dict[str, Any]:
    """
    Verifies that unauthorized or admin-restricted tool calls are properly rejected.
    Supports:
      - (was_denied: bool, expected_denial: bool)
      - (result_status: str, error_output: str, expected_denial: bool)
    """
    if len(args) == 2 and isinstance(args[0], bool) and isinstance(args[1], bool):
        was_denied, exp_denied = args
        passed = (was_denied == exp_denied)
        return {"passed": passed, "was_denied": was_denied, "expected_denied": exp_denied}
        
    if len(args) == 3:
        result_status, error_output, expected_denial = args
        if expected_denial:
            is_denied = (result_status == "error") and any(
                w in error_output.lower() for w in ["requires administrative", "requires authentication", "not allowed", "denied"]
            )
            return {"passed": is_denied, "was_denied": is_denied, "expected_denied": True}
        else:
            is_ok = (result_status != "error")
            return {"passed": is_ok, "was_denied": not is_ok, "expected_denied": False}

    was_denied = kwargs.get("was_denied", False)
    exp_denied = kwargs.get("expected_denial", False)
    return {"passed": was_denied == exp_denied, "was_denied": was_denied, "expected_denied": exp_denied}
